/**
 * MapBiomas Chile — Revision QA muestras anuales SSL4EO
 *
 * Uso: Earth Engine Code Editor > New > App > pegar este script.
 * Requiere asset base con campos QA (poly_uid, poly_qa, rect_qa, ...).
 *
 * Flujo:
 *   1. Seleccionar rectangulo-año en cola izquierda
 *   2. Completar gate rect_qa
 *   3. Revisar poligonos (formulario) o acciones batch por clase
 *   4. Guardar borrador JSON
 *   5. Publicar version (Export.table.toAsset) o usar scripts/06_publish_qa_version.py
 */

// ─── Configuración ───────────────────────────────────────────────────────────
var GEE_PROJECT = 'mapbiomas-chile';
var BASE_ASSET = 'projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_LABELS_SSL4EO/annual_samples';
var PUBLISH_BASE = 'projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_LABELS_SSL4EO';
var QA_SCHEMA_VERSION = '1';

var COV_TARGET = {0: 100, 1: 85, 2: 90, 3: 95};

// ─── Estado cliente ────────────────────────────────────────────────────────────
var qaEdits = {};       // poly_uid -> propiedades editadas
var rectEdits = {};     // rectKey -> {rect_qa, rect_note, qa_user, qa_date}
var currentRectKey = null;
var currentPolyUid = null;
var rectFeatureList = [];  // cache client-side del rect activo

// ─── Datos base ──────────────────────────────────────────────────────────────
var baseFc = ee.FeatureCollection(BASE_ASSET);

// Lista de rectangulos-año (agregado server-side)
var rectList = ee.Dictionary(
  baseFc.reduceColumns(ee.Reducer.toList().group(1, 'rect_key'), ['rect_key'])
    .get('groups')
).keys();  // fallback: construir en cliente

// Construir rect_key en server
var withRectKey = baseFc.map(function(f) {
  var gid = ee.String(f.get('grid_id'));
  var yr = ee.String(f.get('rev_year'));
  return f.set('rect_key', gid.cat('|').cat(yr));
});

// ─── Utilidades ──────────────────────────────────────────────────────────────
function todayIso() {
  var d = new Date();
  return d.getFullYear() + '-' +
    ('0' + (d.getMonth() + 1)).slice(-2) + '-' +
    ('0' + d.getDate()).slice(-2);
}

function rectKeyFromParts(gridId, revYear) {
  return String(gridId) + '|' + String(revYear);
}

function covTargetForTier(tier) {
  tier = Number(tier);
  return COV_TARGET[tier] || COV_TARGET[2];
}

function computeCovRectClient(features) {
  var total = 0;
  var approved = 0;
  features.forEach(function(f) {
    var ha = Number(f.properties.area_ha) || 0;
    total += ha;
    var uid = f.properties.poly_uid;
    var qa = qaEdits[uid] ? qaEdits[uid].poly_qa : (f.properties.poly_qa || '');
    if (qa === 'aprobado') { approved += ha; }
  });
  return total > 0 ? (approved / total * 100) : 0;
}

function mergedProps(feature) {
  var p = feature.properties;
  var uid = p.poly_uid;
  var edit = qaEdits[uid] || {};
  var out = {};
  Object.keys(p).forEach(function(k) { out[k] = p[k]; });
  Object.keys(edit).forEach(function(k) { out[k] = edit[k]; });
  var corr = Number(out.corr_id);
  if (corr > 0 && corr !== -9999) {
    out.lbl_id = corr;
  } else {
    out.lbl_id = Number(out.class_id);
  }
  return out;
}

function polyStyle(feature) {
  var p = mergedProps(feature);
  var qa = p.poly_qa || '';
  var color = '#9e9e9e';
  if (qa === 'aprobado') { color = '#2e7d32'; }
  if (qa === 'rechazado') { color = '#c62828'; }
  return {color: color, fillColor: color, width: 1, fillOpacity: 0.35};
}

// ─── Capas Landsat / NDVI ────────────────────────────────────────────────────
function landsatRgb(geometry, year) {
  year = ee.Number(year);
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = ee.Date.fromYMD(year, 12, 31);
  var collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
    .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
    .filterBounds(geometry)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUD_COVER', 40));
  var img = collection.map(function(i) {
    return i.select(['SR_B4', 'SR_B3', 'SR_B2'], ['red', 'green', 'blue'])
      .multiply(0.0000275).add(-0.2)
      .copyProperties(i, ['system:time_start']);
  }).median();
  return img.clip(geometry);
}

function landsatNdvi(geometry, year) {
  year = ee.Number(year);
  var start = ee.Date.fromYMD(year, 1, 1);
  var end = ee.Date.fromYMD(year, 12, 31);
  var collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
    .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
    .filterBounds(geometry)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUD_COVER', 40));
  return collection.map(function(i) {
    return i.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI');
  }).median().clip(geometry);
}

var landsatLayer = ui.Map.Layer({name: 'Landsat RGB', visParams: {min: 0, max: 0.3, bands: ['red', 'green', 'blue']}, shown: true});
var ndviLayer = ui.Map.Layer({name: 'NDVI', visParams: {min: 0, max: 0.8, palette: ['#8c510a', '#f6e8c3', '#5ab4ac', '#01665e']}, shown: false});
var polyLayer = ui.Map.Layer({name: 'Poligonos QA', visParams: {}, shown: true});

// ─── Mapa ────────────────────────────────────────────────────────────────────
var map = ui.Map();
map.setCenter(-71.5, -35.5, 5);
map.add(landsatLayer);
map.add(ndviLayer);
map.add(polyLayer);

// ─── Widgets: cola izquierda ─────────────────────────────────────────────────
var queueStatus = ui.Label('Cargando cola...', {fontSize: '12px', color: '#555'});
var filterUtm = ui.Select({items: ['Todos', 'UTM18', 'UTM19'], value: 'Todos', placeholder: 'UTM'});
var filterTier = ui.Select({items: ['Todos', '1', '2', '3'], value: 'Todos', placeholder: 'rev_tier'});
var filterRectQa = ui.Select({
  items: ['Todos', 'pendiente', 'aprobado', 'parcial', 'rechazado'],
  value: 'pendiente',
  placeholder: 'rect_qa'
});
var rectSelect = ui.Select({placeholder: 'Seleccione rectangulo-año', onChange: onRectSelected});
var queuePanel = ui.Panel([
  ui.Label('Cola de revision', {fontWeight: 'bold', fontSize: '14px'}),
  queueStatus,
  ui.Label('Filtros'),
  filterUtm, filterTier, filterRectQa,
  ui.Button('Actualizar cola', rebuildQueue),
  ui.Label('Rectangulo-año'),
  rectSelect
], ui.Panel.Layout.flow('vertical'), {width: '280px', padding: '8px'});

// ─── Widgets: formulario derecho ─────────────────────────────────────────────
var rectGateLabel = ui.Label('Gate rectangulo-año', {fontWeight: 'bold'});
var rectQaSelect = ui.Select({
  items: ['pendiente', 'aprobado', 'rechazado', 'parcial'],
  value: 'pendiente',
  onChange: onRectQaChanged
});
var rectNote = ui.Textbox({placeholder: 'rect_note (opcional)', style: {width: '100%'}});
var qaUserBox = ui.Textbox({placeholder: 'qa_user (iniciales)', style: {width: '100%'}});
var covMeter = ui.Label('cov_rect: —', {fontWeight: 'bold'});
var covTargetLabel = ui.Label('Meta: —', {fontSize: '11px', color: '#666'});

var polyInfo = ui.Label('Seleccione un poligono en el mapa', {whiteSpace: 'pre-wrap', fontSize: '11px'});
var polyQaSelect = ui.Select({items: ['', 'aprobado', 'rechazado'], value: '', placeholder: 'poly_qa'});
var qaScopeSelect = ui.Select({items: ['auto', 'poligono', 'clase'], value: 'poligono'});
var corrIdBox = ui.Textbox({placeholder: 'corr_id (opcional)', style: {width: '100%'}});
var errTypeSelect = ui.Select({
  items: ['ninguno', 'clase', 'borde', 'sombra', 'agua', 'nube', 'otro'],
  value: 'ninguno'
});
var polyNoteBox = ui.Textbox({placeholder: 'poly_note', style: {width: '100%'}});

var batchClassSelect = ui.Select({placeholder: 'class_id para batch'});
var batchPanel = ui.Panel([
  ui.Label('Acciones batch', {fontWeight: 'bold'}),
  batchClassSelect,
  ui.Button('Aprobar clase', function() { batchClassAction('aprobado'); }),
  ui.Button('Rechazar clase', function() { batchClassAction('rechazado'); }),
  ui.Button('Aprobar clases >= 5%', batchApproveGte5),
  ui.Button('Rechazar parches < 1%', batchRejectLt1),
  ui.Button('Rechazar todo rect-año', rejectAllRect)
], ui.Panel.Layout.flow('vertical'));

var versionInput = ui.Textbox({placeholder: 'Version publicar (ej. v1)', style: {width: '120px'}});

var draftPanel = ui.Panel([
  ui.Label('Borrador / publicar', {fontWeight: 'bold'}),
  ui.Button('Guardar borrador JSON', saveDraft),
  ui.Textbox({placeholder: 'Pegar JSON borrador para cargar', style: {width: '100%'}, onChange: loadDraftFromText}),
  versionInput,
  ui.Button('Publicar en GEE', publishVersion)
], ui.Panel.Layout.flow('vertical'));

var formPanel = ui.Panel([
  ui.Label('Revision QA', {fontWeight: 'bold', fontSize: '14px'}),
  rectGateLabel, rectQaSelect, rectNote, qaUserBox,
  covMeter, covTargetLabel,
  ui.Button('Guardar gate rect-año', saveRectGate),
  ui.Label('Poligono', {fontWeight: 'bold', margin: '8px 0 0 0'}),
  polyInfo,
  ui.Label('poly_qa'), polyQaSelect,
  ui.Label('qa_scope'), qaScopeSelect,
  ui.Label('corr_id'), corrIdBox,
  ui.Label('err_type'), errTypeSelect,
  ui.Label('poly_note'), polyNoteBox,
  ui.Button('Guardar poligono', savePolygonForm),
  batchPanel,
  draftPanel
], ui.Panel.Layout.flow('vertical'), {width: '320px', padding: '8px'});

// ─── Lógica cola ─────────────────────────────────────────────────────────────
var allRectMeta = [];

function rebuildQueue() {
  queueStatus.setValue('Cargando...');
  withRectKey.reduceColumns({
    reducer: ee.Reducer.first(),
    selectors: [
      'rect_key', 'grid_id', 'rev_year', 'utm', 'rev_tier', 'rev_prior',
      'samp_type', 'rect_qa', 'rare_class', 'rev_desc'
    ]
  }).evaluate(function(result, error) {
    if (error) {
      queueStatus.setValue('Error: ' + error);
      return;
    }
    var features = result.features || [];
    allRectMeta = features.map(function(f) {
      var p = f.properties;
      var rk = p.rect_key;
      return {
        rect_key: rk,
        grid_id: p.grid_id,
        rev_year: p.rev_year,
        utm: p.utm,
        rev_tier: p.rev_tier,
        rev_prior: p.rev_prior,
        samp_type: p.samp_type,
        rect_qa: rectEdits[rk] ? rectEdits[rk].rect_qa : (p.rect_qa || 'pendiente'),
        rare_class: p.rare_class || '',
        rev_desc: p.rev_desc || ''
      };
    });
    allRectMeta.sort(function(a, b) {
      if (a.rev_prior !== b.rev_prior) { return Number(a.rev_prior) - Number(b.rev_prior); }
      if (a.rev_tier !== b.rev_tier) { return Number(a.rev_tier) - Number(b.rev_tier); }
      if (a.samp_type.indexOf('homogenea') >= 0 && b.samp_type.indexOf('homogenea') < 0) { return -1; }
      if (b.samp_type.indexOf('homogenea') >= 0 && a.samp_type.indexOf('homogenea') < 0) { return 1; }
      return String(a.grid_id).localeCompare(String(b.grid_id));
    });
    applyQueueFilters();
  });
}

function applyQueueFilters() {
  var utm = filterUtm.getValue();
  var tier = filterTier.getValue();
  var rqa = filterRectQa.getValue();
  var filtered = allRectMeta.filter(function(r) {
    if (utm !== 'Todos' && String(r.utm) !== utm) { return false; }
    if (tier !== 'Todos' && String(r.rev_tier) !== tier) { return false; }
    if (rqa !== 'Todos' && String(r.rect_qa) !== rqa) { return false; }
    return true;
  });
  var labels = filtered.map(function(r) {
    return r.rect_key + ' | ' + r.samp_type + ' | tier' + r.rev_tier + ' | ' + r.rect_qa;
  });
  rectSelect.setItems(labels);
  queueStatus.setValue('Rect-año: ' + filtered.length + ' / ' + allRectMeta.length);
}

filterUtm.onChange(applyQueueFilters);
filterTier.onChange(applyQueueFilters);
filterRectQa.onChange(applyQueueFilters);

// ─── Seleccion rectangulo ─────────────────────────────────────────────────────
function onRectSelected(label) {
  if (!label) { return; }
  var rectKey = label.split(' | ')[0];
  currentRectKey = rectKey;
  var parts = rectKey.split('|');
  var gridId = parts[0];
  var revYear = parts[1];
  var fc = withRectKey.filter(ee.Filter.eq('rect_key', rectKey));
  fc.evaluate(function(result, error) {
    if (error) {
      polyInfo.setValue('Error cargando rect: ' + error);
      return;
    }
    rectFeatureList = result.features || [];
    updateRectForm(rectKey);
    updateBatchClassList();
    updateCovMeter();
    drawPolygons();
    updateLandsatLayers(gridId, revYear);
  });
}

function updateRectForm(rectKey) {
  var meta = allRectMeta.filter(function(r) { return r.rect_key === rectKey; })[0];
  if (!meta) { return; }
  var re = rectEdits[rectKey] || {};
  rectGateLabel.setValue('Gate: ' + rectKey + '\n' + meta.samp_type + ' | tier ' + meta.rev_tier);
  rectQaSelect.setValue(re.rect_qa || meta.rect_qa || 'pendiente');
  rectNote.setValue(re.rect_note || '');
  covTargetLabel.setValue('Meta cov_rect: ' + covTargetForTier(meta.rev_tier) + '%');
}

function updateBatchClassList() {
  var byClass = {};
  rectFeatureList.forEach(function(f) {
    var cid = String(f.properties.class_id);
    var ha = Number(f.properties.area_ha) || 0;
    if (!byClass[cid]) { byClass[cid] = {ha: 0, nm: f.properties.class_nm}; }
    byClass[cid].ha += ha;
  });
  var rectHa = rectFeatureList.reduce(function(s, f) {
    return s + (Number(f.properties.area_ha) || 0);
  }, 0);
  var items = Object.keys(byClass).map(function(cid) {
    var pct = rectHa > 0 ? (byClass[cid].ha / rectHa * 100).toFixed(1) : '0';
    return cid + ' — ' + byClass[cid].nm + ' (' + pct + '%)';
  });
  batchClassSelect.setItems(items);
}

function drawPolygons() {
  var features = rectFeatureList.map(function(f) {
    var p = mergedProps(f);
    var qa = p.poly_qa || '';
    var color = '#9e9e9e';
    if (qa === 'aprobado') { color = '#2e7d32'; }
    if (qa === 'rechazado') { color = '#c62828'; }
    return ee.Feature(ee.Geometry(f.geometry), p).set('_color', color);
  });
  var fc = ee.FeatureCollection(features);
  polyLayer.setEeObject(fc.style({
    color: {property: '_color'},
    fillColor: {property: '_color'},
    width: 1,
    fillOpacity: 0.35
  }));
  if (rectFeatureList.length > 0) {
    var bounds = ee.FeatureCollection(rectFeatureList).geometry().bounds();
    bounds.evaluate(function(b) {
      if (b) { map.centerObject(ee.Geometry.Rectangle(b.coordinates[0]), 14); }
    });
  }
}

function updateLandsatLayers(gridId, revYear) {
  var geom = ee.FeatureCollection(rectFeatureList).geometry();
  var year = Number(revYear);
  var meta = allRectMeta.filter(function(r) { return r.rect_key === currentRectKey; })[0];
  var tier = meta ? Number(meta.rev_tier) : 2;
  landsatLayer.setEeObject(landsatRgb(geom, year));
  if (tier >= 2) {
    ndviLayer.setEeObject(landsatNdvi(geom, year));
    ndviLayer.setShown(true);
  } else {
    ndviLayer.setShown(false);
  }
}

// ─── Gate rect-año ───────────────────────────────────────────────────────────
function onRectQaChanged(val) {
  if (val === 'rechazado' && currentRectKey) {
    rejectAllRect();
  }
}

function saveRectGate() {
  if (!currentRectKey) { return; }
  var user = qaUserBox.getValue();
  if (!user) {
    polyInfo.setValue('Ingrese qa_user antes de guardar.');
    return;
  }
  rectEdits[currentRectKey] = {
    rect_qa: rectQaSelect.getValue(),
    rect_note: rectNote.getValue(),
    qa_user: user,
    qa_date: todayIso()
  };
  if (rectQaSelect.getValue() === 'rechazado') {
    rejectAllRect();
  }
  if (rectQaSelect.getValue() === 'aprobado') {
    batchApproveGte5();
  }
  rebuildQueue();
  polyInfo.setValue('Gate guardado: ' + currentRectKey);
}

// ─── Poligono ────────────────────────────────────────────────────────────────
map.onClick(function(coords) {
  if (!rectFeatureList.length) { return; }
  var point = ee.Geometry.Point([coords.lon, coords.lat]);
  ee.FeatureCollection(rectFeatureList)
    .filterBounds(point.buffer(30))
    .limit(5)
    .evaluate(function(res, error) {
      if (error || !res.features || !res.features.length) {
        polyInfo.setValue('Sin poligono en click.');
        return;
      }
      showPolygonForm(res.features[0]);
    });
});

function showPolygonForm(feature) {
  var p = mergedProps(feature);
  currentPolyUid = p.poly_uid;
  polyInfo.setValue(
    'poly_uid: ' + p.poly_uid + '\n' +
    'class: ' + p.class_id + ' ' + p.class_nm + '\n' +
    'area: ' + Number(p.area_ha).toFixed(2) + ' ha (' + Number(p.pct_rect).toFixed(2) + '%)\n' +
    'es_transv: ' + p.es_transv + ' | es_crit_n3: ' + p.es_crit_n3
  );
  polyQaSelect.setValue(p.poly_qa || '');
  qaScopeSelect.setValue(p.qa_scope || 'poligono');
  corrIdBox.setValue(p.corr_id > 0 && p.corr_id !== -9999 ? String(p.corr_id) : '');
  errTypeSelect.setValue(p.err_type || 'ninguno');
  polyNoteBox.setValue(p.poly_note || '');
}

function savePolygonForm() {
  if (!currentPolyUid) {
    polyInfo.setValue('Seleccione un poligono primero.');
    return;
  }
  var user = qaUserBox.getValue();
  if (!user) {
    polyInfo.setValue('Ingrese qa_user.');
    return;
  }
  var polyQa = polyQaSelect.getValue();
  if (!polyQa) {
    polyInfo.setValue('Seleccione poly_qa.');
    return;
  }
  var corr = corrIdBox.getValue();
  qaEdits[currentPolyUid] = {
    poly_qa: polyQa,
    qa_scope: qaScopeSelect.getValue() || 'poligono',
    corr_id: corr ? Number(corr) : -9999,
    err_type: polyQa === 'rechazado' ? errTypeSelect.getValue() : 'ninguno',
    poly_note: polyNoteBox.getValue(),
    qa_user: user,
    qa_date: todayIso(),
    qa_ver: QA_SCHEMA_VERSION
  };
  if (corr && Number(corr) > 0) {
    qaEdits[currentPolyUid].lbl_id = Number(corr);
  }
  updateCovMeter();
  drawPolygons();
  polyInfo.setValue('Guardado: ' + currentPolyUid);
}

// ─── Batch ───────────────────────────────────────────────────────────────────
function batchClassAction(status) {
  var sel = batchClassSelect.getValue();
  if (!sel || !rectFeatureList.length) { return; }
  var classId = sel.split(' — ')[0];
  var user = qaUserBox.getValue() || 'batch';
  rectFeatureList.forEach(function(f) {
    if (String(f.properties.class_id) !== classId) { return; }
    var uid = f.properties.poly_uid;
    qaEdits[uid] = {
      poly_qa: status,
      qa_scope: 'clase',
      corr_id: -9999,
      err_type: status === 'rechazado' ? 'clase' : 'ninguno',
      poly_note: '',
      qa_user: user,
      qa_date: todayIso(),
      qa_ver: QA_SCHEMA_VERSION,
      lbl_id: Number(f.properties.class_id)
    };
  });
  updateCovMeter();
  drawPolygons();
}

function batchApproveGte5() {
  var rectHa = rectFeatureList.reduce(function(s, f) {
    return s + (Number(f.properties.area_ha) || 0);
  }, 0);
  var user = qaUserBox.getValue() || 'batch';
  rectFeatureList.forEach(function(f) {
    var ha = Number(f.properties.area_ha) || 0;
    var pct = rectHa > 0 ? (ha / rectHa * 100) : 0;
    if (pct < 5) { return; }
    var uid = f.properties.poly_uid;
    qaEdits[uid] = {
      poly_qa: 'aprobado',
      qa_scope: 'clase',
      corr_id: -9999,
      err_type: 'ninguno',
      poly_note: '',
      qa_user: user,
      qa_date: todayIso(),
      qa_ver: QA_SCHEMA_VERSION,
      lbl_id: Number(f.properties.class_id)
    };
  });
  updateCovMeter();
  drawPolygons();
}

function batchRejectLt1() {
  var rectHa = rectFeatureList.reduce(function(s, f) {
    return s + (Number(f.properties.area_ha) || 0);
  }, 0);
  var user = qaUserBox.getValue() || 'batch';
  rectFeatureList.forEach(function(f) {
    var ha = Number(f.properties.area_ha) || 0;
    var pct = rectHa > 0 ? (ha / rectHa * 100) : 0;
    if (pct >= 1) { return; }
    var uid = f.properties.poly_uid;
    qaEdits[uid] = {
      poly_qa: 'rechazado',
      qa_scope: 'auto',
      corr_id: -9999,
      err_type: 'borde',
      poly_note: 'auto <1%',
      qa_user: user,
      qa_date: todayIso(),
      qa_ver: QA_SCHEMA_VERSION,
      lbl_id: Number(f.properties.class_id)
    };
  });
  updateCovMeter();
  drawPolygons();
}

function rejectAllRect() {
  if (!rectFeatureList.length) { return; }
  var user = qaUserBox.getValue() || 'batch';
  rectFeatureList.forEach(function(f) {
    var uid = f.properties.poly_uid;
    qaEdits[uid] = {
      poly_qa: 'rechazado',
      qa_scope: 'auto',
      corr_id: -9999,
      err_type: 'clase',
      poly_note: 'rect rechazado',
      qa_user: user,
      qa_date: todayIso(),
      qa_ver: QA_SCHEMA_VERSION,
      lbl_id: Number(f.properties.class_id)
    };
  });
  if (currentRectKey) {
    rectEdits[currentRectKey] = {
      rect_qa: 'rechazado',
      rect_note: rectNote.getValue(),
      qa_user: user,
      qa_date: todayIso()
    };
    rectQaSelect.setValue('rechazado');
  }
  updateCovMeter();
  drawPolygons();
}

function updateCovMeter() {
  var cov = computeCovRectClient(rectFeatureList);
  covMeter.setValue('cov_rect: ' + cov.toFixed(1) + '%');
  if (currentRectKey) {
    var meta = allRectMeta.filter(function(r) { return r.rect_key === currentRectKey; })[0];
    var target = meta ? covTargetForTier(meta.rev_tier) : 90;
    covMeter.style().set('color', cov >= target ? '#2e7d32' : '#e65100');
  }
}

// ─── Borrador / publicar ─────────────────────────────────────────────────────
function buildDraftObject() {
  return {
    qa_schema: QA_SCHEMA_VERSION,
    qa_user: qaUserBox.getValue(),
    qa_date: todayIso(),
    base_asset: BASE_ASSET,
    edits: qaEdits,
    rect_edits: rectEdits
  };
}

function saveDraft() {
  var json = JSON.stringify(buildDraftObject(), null, 2);
  print('=== BORRADOR QA JSON (copiar o descargar desde consola) ===');
  print(json);
  polyInfo.setValue('Borrador impreso en consola (' + Object.keys(qaEdits).length + ' poligonos).');
}

function loadDraftFromText(text) {
  if (!text) { return; }
  try {
    var data = JSON.parse(text);
    qaEdits = data.edits || {};
    rectEdits = data.rect_edits || {};
    if (data.qa_user) { qaUserBox.setValue(data.qa_user); }
    rebuildQueue();
    if (currentRectKey) { onRectSelected(rectSelect.getValue()); }
    polyInfo.setValue('Borrador cargado: ' + Object.keys(qaEdits).length + ' poligonos.');
  } catch (e) {
    polyInfo.setValue('JSON invalido: ' + e);
  }
}

function publishVersion() {
  var version = versionInput.getValue();
  if (!version) {
    polyInfo.setValue('Indique version (ej. v1).');
    return;
  }
  var assetId = PUBLISH_BASE + '/annual_samples_' + version;
  var editKeys = Object.keys(qaEdits);
  if (!editKeys.length) {
    polyInfo.setValue('No hay ediciones para publicar.');
    return;
  }

  var editFeatures = editKeys.map(function(uid) {
    var e = qaEdits[uid];
    return ee.Feature(null, {
      poly_uid: uid,
      poly_qa: e.poly_qa || '',
      qa_scope: e.qa_scope || 'poligono',
      corr_id: e.corr_id || -9999,
      err_type: e.err_type || 'ninguno',
      poly_note: e.poly_note || '',
      qa_user: e.qa_user || '',
      qa_date: e.qa_date || todayIso(),
      lbl_id: e.lbl_id || -9999,
      qa_ver: QA_SCHEMA_VERSION
    });
  });
  var editsFc = ee.FeatureCollection(editFeatures);

  var merged = baseFc.map(function(f) {
    var uid = ee.String(f.get('poly_uid'));
    var match = editsFc.filter(ee.Filter.eq('poly_uid', uid)).first();
    return ee.Algorithms.If(
      match,
      f.copyProperties(match, null, true),
      f
    );
  });

  Export.table.toAsset({
    collection: merged,
    description: 'annual_samples_' + version,
    assetId: assetId
  });
  polyInfo.setValue(
    'Export iniciado: ' + assetId + '\nRevise Tasks.\n' +
    'Para merge completo (334k poligonos) use scripts/06_publish_qa_version.py'
  );
}

// ─── Layout ──────────────────────────────────────────────────────────────────
ui.root.clear();
ui.root.add(ui.Panel([
  queuePanel,
  map,
  formPanel
], ui.Panel.Layout.flow('horizontal'), {stretch: 'both'}));

rebuildQueue();
