"""Diccionarios de clases y ecorregiones — IDs nativos MapBiomas C2."""

ECO_NAMES = {
    1: "E1_Puna_seca_andina_central",
    2: "E2_Desierto_de_Atacama",
    3: "E3_Matorral_chileno_norte_1",
    4: "E4_Estepa_andina",
    5: "E5_Matorral_chileno_norte_2",
    6: "E6_Andes_norte",
    7: "E7_Andes_central",
    8: "E8_Matorral_chileno_sur",
    9: "E9_Costa_Norte",
    10: "E10_Andes_Sur",
    11: "E11_Costa_Sur_1",
    12: "E12_Costa_Sur_2",
    13: "E13_Andes_Sur_Costa",
    14: "E14_Estepa_patagonica",
    15: "E15_Bosque_subpolar_magallanico",
    16: "E16_Isla_de_Pascua",
    17: "E17_Archipielago_Juan_Fernandez",
}

CLASS_NAMES = {
    1: "Formacion_boscosa",
    3: "Bosque",
    59: "Bosque_primario",
    60: "Bosque_secundario",
    67: "Bosque_achaparrado",
    10: "Formacion_natural_no_boscosa",
    12: "Pastizal",
    63: "Estepa",
    66: "Matorral",
    14: "Agropecuaria_y_silvicultura",
    15: "Pastura",
    22: "Area_sin_vegetacion",
    23: "Arena_playa_duna",
    61: "Salar",
    29: "Afloramiento_rocoso",
    25: "Otra_area_sin_vegetacion",
    26: "Cuerpo_de_agua",
    33: "Rio_lago_oceano",
    27: "No_observado",
    11: "Humedal",
    73: "Turbera",
    74: "Otro_humedal",
    18: "Agricultura",
    19: "Agricultura_temporal",
    36: "Agricultura_perenne",
    9: "Silvicultura",
    79: "Silvicultura_coniferas",
    80: "Silvicultura_latifoliadas",
    24: "Zona_urbana",
    30: "Mineria",
    75: "Fotovoltaica",
    34: "Glaciar",
    35: "Nieve",
}

CLASES_MODELO_GENERAL = [3, 12, 15, 23, 25, 29, 59, 60, 61, 63, 66, 67]
CLASES_TRANSVERSALES = [9, 11, 18, 19, 24, 30, 36, 73, 74, 75, 79, 80]
CLASES_MASCARA = [26, 33, 34, 35]
CLASES_PROTEGIDAS = [3, 23, 61, 67]

# Pares teóricos provisionales. Excluir 60/67 como pares de 3 al norte de 23.2°S
# (ver espacial.py). Sustituir por matriz de confusión RF en FASE 2.
CONFUSION_PAIRS = {
    1: [10, 66],
    3: [66, 10],  # sin 60/67: no coexisten geográficamente con tamarugo
    59: [66, 60, 3],
    60: [66, 3, 67, 10],
    67: [66, 60, 12, 10],
    10: [66, 12, 63, 3],
    12: [63, 15, 66, 10],
    63: [12, 15, 66, 10],
    66: [3, 60, 12, 63, 10],
    14: [15, 12, 63],
    15: [12, 63, 14],
    22: [29, 25, 23, 61],
    23: [61, 29, 25],
    61: [23, 25, 29],
    29: [23, 25, 61, 22],
    25: [29, 23, 61, 22],
    26: [33],
    33: [26],
    27: [],
}

BBOX_CLASE = {
    3: {
        "epsg": 32719,
        "xmin": 399124.336,
        "ymin": 7436881.249,
        "xmax": 595032.981,
        "ymax": 7828586.655,
    },
}
