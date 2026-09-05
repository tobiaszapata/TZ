"""
Estructura de la canasta IPC y ponderadores oficiales, PARA LAS 6 REGIONES.

FUENTE: ponderadores_ipc.xls (INDEC), las seis columnas regionales.
Verificado: las divisiones suman 1,0000 en cada region.

POR QUE REGIONAL Y NO SOLO GBA:
SEPA es nacional. Una version anterior de este archivo filtraba todo a GBA
para no mezclar precios de Cordoba en un indice ponderado con pesos del
conurbano — pero eso tiraba el 60% de los datos. La solucion correcta es
calcular UN INDICE POR REGION, cada uno con sus propios ponderadores, y
despues combinarlos con la importancia relativa de cada region para llegar
al nacional. Es exactamente lo que hace INDEC.

Los pesos regionales difieren bastante: Alimentos pesa 23,4% en GBA pero
35,3% en el Noreste. Usar los de GBA en todo el pais seria un error
sistematico, no un detalle.
"""

from dataclasses import dataclass
from enum import Enum

REGIONES = ["GBA", "Pampeana", "Noreste", "Noroeste", "Cuyo", "Patagonia"]

# Importancia de cada region en el indice nacional.
# FUENTE: tabla oficial de INDEC con 2 decimales de precision (provista
# directamente, no la version redondeada a 3 decimales de la Metodologia
# N32 que se usaba antes). Suma EXACTA 1.0 sin necesidad de normalizar:
# 44.67 + 34.19 + 4.51 + 6.88 + 5.18 + 4.57 = 100.00
#
# HISTORIAL: la version anterior usaba los valores de la Metodologia N32
# Cuadro 6 redondeados a 3 decimales (0.447, 0.342, 0.069, 0.045, 0.052,
# 0.046), que sumaban 1.001 en vez de 1.000 -- un error real detectado al
# comparar un calculo manual contra el del sistema (el peso nacional de
# Alimentos daba 26.996% en la version con error, 26.969% con la
# normalizacion proporcional de ese error, y ahora 26.934% exacto con
# estos valores mas precisos, que coincide con el calculo manual).
PESO_REGION = {
    "GBA": 0.4467, "Pampeana": 0.3419, "Noroeste": 0.0688,
    "Noreste": 0.0451, "Cuyo": 0.0518, "Patagonia": 0.0457,
}


class Cobertura(str, Enum):
    MEDIDA_SEPA = "medida_sepa"
    PENDIENTE = "pendiente"
    NO_SCRAPEABLE = "no_scrapeable"
    EXCLUIDA = "excluida"          # existe, pero se decidio no medirla


@dataclass(frozen=True)
class Item:
    codigo: str
    nombre: str
    nivel: str              # "division" | "grupo" | "clase"
    padre: str | None
    pesos: dict             # {region: ponderador} — fraccion, no %
    cobertura: Cobertura = Cobertura.PENDIENTE

    def peso(self, region: str = "GBA") -> float:
        return self.pesos.get(region, 0.0)


ITEMS = [
    Item("01", "Alimentos y bebidas no alcohólicas", "division", None, {"GBA": 0.2344, "Pampeana": 0.2865, "Noreste": 0.353, "Noroeste": 0.3467, "Cuyo": 0.2842, "Patagonia": 0.2743}, Cobertura.PENDIENTE),
    Item("01.1", "Alimentos", "grupo", '01', {"GBA": 0.2033, "Pampeana": 0.2573, "Noreste": 0.3166, "Noroeste": 0.3031, "Cuyo": 0.2547, "Patagonia": 0.2477}, Cobertura.PENDIENTE),
    Item("01.1.1", "Pan y cereales", "clase", '01.1', {"GBA": 0.0405, "Pampeana": 0.0502, "Noreste": 0.0659, "Noroeste": 0.0649, "Cuyo": 0.0521, "Patagonia": 0.0461}, Cobertura.MEDIDA_SEPA),
    Item("01.1.2", "Carnes y derivados", "clase", '01.1', {"GBA": 0.0698, "Pampeana": 0.0981, "Noreste": 0.1327, "Noroeste": 0.125, "Cuyo": 0.1032, "Patagonia": 0.0992}, Cobertura.MEDIDA_SEPA),
    Item("01.1.3", "Pescados y mariscos", "clase", '01.1', {"GBA": 0.0051, "Pampeana": 0.0047, "Noreste": 0.0029, "Noroeste": 0.0034, "Cuyo": 0.0045, "Patagonia": 0.0048}, Cobertura.MEDIDA_SEPA),
    Item("01.1.4", "Leche, productos lácteos, huevos y alimentos vegetales", "clase", '01.1', {"GBA": 0.0345, "Pampeana": 0.0373, "Noreste": 0.041, "Noroeste": 0.0369, "Cuyo": 0.0355, "Patagonia": 0.0368}, Cobertura.MEDIDA_SEPA),
    Item("01.1.5", "Aceites, grasas y manteca", "clase", '01.1', {"GBA": 0.0055, "Pampeana": 0.0076, "Noreste": 0.009, "Noroeste": 0.0064, "Cuyo": 0.0066, "Patagonia": 0.0063}, Cobertura.MEDIDA_SEPA),
    Item("01.1.6", "Frutas", "clase", '01.1', {"GBA": 0.0127, "Pampeana": 0.0146, "Noreste": 0.0146, "Noroeste": 0.0145, "Cuyo": 0.011, "Patagonia": 0.0128}, Cobertura.MEDIDA_SEPA),
    Item("01.1.7", "Verduras, tubérculos y legumbres", "clase", '01.1', {"GBA": 0.0223, "Pampeana": 0.029, "Noreste": 0.0359, "Noroeste": 0.0358, "Cuyo": 0.0279, "Patagonia": 0.0268}, Cobertura.MEDIDA_SEPA),
    Item("01.1.8", "Azúcar, dulces, chocolate, golosinas, etc.", "clase", '01.1', {"GBA": 0.0101, "Pampeana": 0.0121, "Noreste": 0.0112, "Noroeste": 0.0124, "Cuyo": 0.0103, "Patagonia": 0.0102}, Cobertura.MEDIDA_SEPA),
    Item("01.1.9", "Otros alimentos", "clase", '01.1', {"GBA": 0.0029, "Pampeana": 0.0037, "Noreste": 0.0036, "Noroeste": 0.0036, "Cuyo": 0.0036, "Patagonia": 0.0048}, Cobertura.MEDIDA_SEPA),
    Item("01.2", "Bebidas no alcohólicas", "grupo", '01', {"GBA": 0.0311, "Pampeana": 0.0292, "Noreste": 0.0364, "Noroeste": 0.0436, "Cuyo": 0.0295, "Patagonia": 0.0266}, Cobertura.PENDIENTE),
    Item("01.2.1", "Café, té, yerba y cacao", "clase", '01.2', {"GBA": 0.0068, "Pampeana": 0.0082, "Noreste": 0.0093, "Noroeste": 0.0064, "Cuyo": 0.0066, "Patagonia": 0.0069}, Cobertura.MEDIDA_SEPA),
    Item("01.2.2", "Aguas minerales, bebidas gaseosas y jugos", "clase", '01.2', {"GBA": 0.0243, "Pampeana": 0.021, "Noreste": 0.0271, "Noroeste": 0.0372, "Cuyo": 0.0229, "Patagonia": 0.0197}, Cobertura.MEDIDA_SEPA),
    Item("02", "Bebidas alcohólicas y tabaco", "division", None, {"GBA": 0.0327, "Pampeana": 0.038, "Noreste": 0.0364, "Noroeste": 0.0313, "Cuyo": 0.0357, "Patagonia": 0.035}, Cobertura.PENDIENTE),
    Item("02.1", "Bebidas alcohólicas", "grupo", '02', {"GBA": 0.0142, "Pampeana": 0.0179, "Noreste": 0.0204, "Noroeste": 0.0137, "Cuyo": 0.0142, "Patagonia": 0.014}, Cobertura.PENDIENTE),
    Item("02.1.1", "Bebidas espirituosas, destiladas y licores", "clase", '02.1', {"GBA": 0.0006, "Pampeana": 0.0006, "Noreste": 0.0003, "Noroeste": 0.0007, "Cuyo": 0.0005, "Patagonia": 0.0009}, Cobertura.MEDIDA_SEPA),
    Item("02.1.2", "Vinos", "clase", '02.1', {"GBA": 0.0107, "Pampeana": 0.0139, "Noreste": 0.0145, "Noroeste": 0.0102, "Cuyo": 0.0111, "Patagonia": 0.01}, Cobertura.MEDIDA_SEPA),
    Item("02.1.3", "Cerveza", "clase", '02.1', {"GBA": 0.0029, "Pampeana": 0.0034, "Noreste": 0.0056, "Noroeste": 0.0029, "Cuyo": 0.0026, "Patagonia": 0.0031}, Cobertura.MEDIDA_SEPA),
    Item("02.2", "Tabaco", "grupo", '02', {"GBA": 0.0185, "Pampeana": 0.0201, "Noreste": 0.016, "Noroeste": 0.0176, "Cuyo": 0.0215, "Patagonia": 0.021}, Cobertura.PENDIENTE),
    Item("03", "Prendas de vestir y calzado", "division", None, {"GBA": 0.0849, "Pampeana": 0.1043, "Noreste": 0.116, "Noroeste": 0.1237, "Cuyo": 0.1138, "Patagonia": 0.1282}, Cobertura.PENDIENTE),
    Item("03.1", "Prendas de vestir y materiales", "grupo", '03', {"GBA": 0.0633, "Pampeana": 0.0768, "Noreste": 0.0797, "Noroeste": 0.0838, "Cuyo": 0.0826, "Patagonia": 0.0896}, Cobertura.PENDIENTE),
    Item("03.1.1", "Materiales textiles, telas e hilados", "clase", '03.1', {"GBA": 0.0009, "Pampeana": 0.0009, "Noreste": 0.0006, "Noroeste": 0.0009, "Cuyo": 0.001, "Patagonia": 0.0011}, Cobertura.PENDIENTE),
    Item("03.1.2", "Prendas de vestir", "clase", '03.1', {"GBA": 0.0576, "Pampeana": 0.0726, "Noreste": 0.0762, "Noroeste": 0.0795, "Cuyo": 0.0782, "Patagonia": 0.085}, Cobertura.MEDIDA_SEPA),
    Item("03.1.3", "Otros artículos y accesorios para el vestir", "clase", '03.1', {"GBA": 0.0025, "Pampeana": 0.0022, "Noreste": 0.0023, "Noroeste": 0.0025, "Cuyo": 0.0023, "Patagonia": 0.0025}, Cobertura.PENDIENTE),
    Item("03.1.4", "Limpieza, reparación, alquiler de ropa", "clase", '03.1', {"GBA": 0.0025, "Pampeana": 0.0011, "Noreste": 0.0006, "Noroeste": 0.0008, "Cuyo": 0.0011, "Patagonia": 0.0009}, Cobertura.PENDIENTE),
    Item("03.2", "Calzado", "grupo", '03', {"GBA": 0.0215, "Pampeana": 0.0275, "Noreste": 0.0363, "Noroeste": 0.04, "Cuyo": 0.0312, "Patagonia": 0.0386}, Cobertura.PENDIENTE),
    Item("03.2.1", "Zapatos y otros calzados", "clase", '03.2', {"GBA": 0.0209, "Pampeana": 0.0271, "Noreste": 0.0355, "Noroeste": 0.0392, "Cuyo": 0.0302, "Patagonia": 0.0381}, Cobertura.MEDIDA_SEPA),
    Item("03.2.2", "Limpieza, reparación y alquiler de calzado", "clase", '03.2', {"GBA": 0.0006, "Pampeana": 0.0004, "Noreste": 0.0008, "Noroeste": 0.0008, "Cuyo": 0.001, "Patagonia": 0.0005}, Cobertura.PENDIENTE),
    Item("04", "Vivienda agua, electricidad y otros combustibles", "division", None, {"GBA": 0.1046, "Pampeana": 0.0867, "Noreste": 0.0811, "Noroeste": 0.07, "Cuyo": 0.0888, "Patagonia": 0.1006}, Cobertura.PENDIENTE),
    Item("04.1", "Alquileres efectivos del alojamiento", "grupo", '04', {"GBA": 0.058, "Pampeana": 0.0391, "Noreste": 0.0236, "Noroeste": 0.0198, "Cuyo": 0.038, "Patagonia": 0.0511}, Cobertura.NO_SCRAPEABLE),
    Item("04.1.1", "Alquileres efectivos pagados por los inquilinos", "clase", '04.1', {"GBA": 0.0348, "Pampeana": 0.0359, "Noreste": 0.0222, "Noroeste": 0.0187, "Cuyo": 0.0367, "Patagonia": 0.0499}, Cobertura.PENDIENTE),
    Item("04.1.3", "Gastos comunes por la vivienda y/o cochera y otros gastos", "clase", '04.1', {"GBA": 0.0232, "Pampeana": 0.0032, "Noreste": 0.0014, "Noroeste": 0.0012, "Cuyo": 0.0014, "Patagonia": 0.0013}, Cobertura.PENDIENTE),
    Item("04.3", "Mantenimiento y reparación de la vivienda", "grupo", '04', {"GBA": 0.0123, "Pampeana": 0.0116, "Noreste": 0.0112, "Noroeste": 0.0071, "Cuyo": 0.0117, "Patagonia": 0.0103}, Cobertura.PENDIENTE),
    Item("04.3.1", "Materiales para la reparación de la vivienda", "clase", '04.3', {"GBA": 0.0052, "Pampeana": 0.005, "Noreste": 0.0057, "Noroeste": 0.0038, "Cuyo": 0.0074, "Patagonia": 0.0069}, Cobertura.PENDIENTE),
    Item("04.3.2", "Servicios para la reparación de la vivienda", "clase", '04.3', {"GBA": 0.007, "Pampeana": 0.0067, "Noreste": 0.0055, "Noroeste": 0.0033, "Cuyo": 0.0043, "Patagonia": 0.0034}, Cobertura.PENDIENTE),
    Item("04.4", "Suministro de agua", "grupo", '04', {"GBA": 0.0089, "Pampeana": 0.0062, "Noreste": 0.0089, "Noroeste": 0.0067, "Cuyo": 0.006, "Patagonia": 0.0098}, Cobertura.PENDIENTE),
    Item("04.5", "Electricidad, gas y otros combustibles", "grupo", '04', {"GBA": 0.0254, "Pampeana": 0.0298, "Noreste": 0.0374, "Noroeste": 0.0364, "Cuyo": 0.0332, "Patagonia": 0.0294}, Cobertura.PENDIENTE),
    Item("04.5.1", "Electricidad", "clase", '04.5', {"GBA": 0.0103, "Pampeana": 0.0108, "Noreste": 0.0276, "Noroeste": 0.0178, "Cuyo": 0.0128, "Patagonia": 0.0181}, Cobertura.PENDIENTE),
    Item("04.5.2", "Gas", "clase", '04.5', {"GBA": 0.0151, "Pampeana": 0.019, "Noreste": 0.0098, "Noroeste": 0.0186, "Cuyo": 0.0203, "Patagonia": 0.0113}, Cobertura.PENDIENTE),
    Item("05", "Equipamiento y mantenimiento del hogar", "division", None, {"GBA": 0.0627, "Pampeana": 0.0634, "Noreste": 0.0778, "Noroeste": 0.0612, "Cuyo": 0.0628, "Patagonia": 0.0655}, Cobertura.PENDIENTE),
    Item("05.1", "Muebles, accesorios, alfombras y otros materiales para pisos", "grupo", '05', {"GBA": 0.006, "Pampeana": 0.0053, "Noreste": 0.0075, "Noroeste": 0.0057, "Cuyo": 0.0062, "Patagonia": 0.009}, Cobertura.PENDIENTE),
    Item("05.1.1", "Muebles, accesorios, alfombras y otros materiales para pisos", "clase", '05.1', {"GBA": 0.006, "Pampeana": 0.0053, "Noreste": 0.0075, "Noroeste": 0.0057, "Cuyo": 0.0062, "Patagonia": 0.009}, Cobertura.PENDIENTE),
    Item("05.2", "Artículos textiles para el hogar", "grupo", '05', {"GBA": 0.0026, "Pampeana": 0.0025, "Noreste": 0.0028, "Noroeste": 0.0028, "Cuyo": 0.0032, "Patagonia": 0.0035}, Cobertura.PENDIENTE),
    # 05.2.1 SI se releva con SEPA: sabanas, toallas, acolchados, cortinas
    # se venden en las secciones de bazar/textil de hiper y supermercados
    # grandes. Ya habia reglas de clasificacion escritas para esto en
    # collectors/sepa/mapeo.py, pero nunca podian aplicarse porque esta
    # clase no estaba declarada — quedaban sin mapear en silencio.
    Item("05.2.1", "Artículos textiles para el hogar", "clase", '05.2', {"GBA": 0.0026, "Pampeana": 0.0025, "Noreste": 0.0028, "Noroeste": 0.0028, "Cuyo": 0.0032, "Patagonia": 0.0035}, Cobertura.MEDIDA_SEPA),
    Item("05.3", "Artefactos para el hogar", "grupo", '05', {"GBA": 0.0114, "Pampeana": 0.0122, "Noreste": 0.0253, "Noroeste": 0.0102, "Cuyo": 0.0104, "Patagonia": 0.0159}, Cobertura.PENDIENTE),
    Item("05.3.1", "Artefactos para el hogar", "clase", '05.3', {"GBA": 0.0114, "Pampeana": 0.0122, "Noreste": 0.0253, "Noroeste": 0.0102, "Cuyo": 0.0104, "Patagonia": 0.0159}, Cobertura.PENDIENTE),
    Item("05.4", "Vajilla, utensilios, loza, cristalería  y otros artículos para el hogar", "grupo", '05', {"GBA": 0.0027, "Pampeana": 0.0026, "Noreste": 0.0035, "Noroeste": 0.0029, "Cuyo": 0.0028, "Patagonia": 0.0039}, Cobertura.PENDIENTE),
    # 05.4.1 SI se releva con SEPA: vasos, platos, ollas, cubiertos — el
    # "bazar" clasico de un supermercado. Mismo caso que 05.2.1: la regla
    # de mapeo.py ya existia, faltaba declarar la clase.
    Item("05.4.1", "Vajilla, utensilios, loza, cristalería y otros artículos para el hogar", "clase", '05.4', {"GBA": 0.0027, "Pampeana": 0.0026, "Noreste": 0.0035, "Noroeste": 0.0029, "Cuyo": 0.0028, "Patagonia": 0.0039}, Cobertura.MEDIDA_SEPA),
    Item("05.5", "Herramientas y equipos para el hogar y el jardín", "grupo", '05', {"GBA": 0.0033, "Pampeana": 0.0027, "Noreste": 0.0031, "Noroeste": 0.0026, "Cuyo": 0.0034, "Patagonia": 0.003}, Cobertura.PENDIENTE),
    Item("05.5.1", "Herramientas y equipos para el hogar y el jardín", "clase", '05.5', {"GBA": 0.0033, "Pampeana": 0.0027, "Noreste": 0.0031, "Noroeste": 0.0026, "Cuyo": 0.0034, "Patagonia": 0.003}, Cobertura.PENDIENTE),
    Item("05.6", "Bienes y servicios para la conservación del hogar", "grupo", '05', {"GBA": 0.0366, "Pampeana": 0.0381, "Noreste": 0.0355, "Noroeste": 0.0369, "Cuyo": 0.0368, "Patagonia": 0.0303}, Cobertura.PENDIENTE),
    Item("05.6.1", "Bienes para el hogar no durables", "clase", '05.6', {"GBA": 0.0167, "Pampeana": 0.0212, "Noreste": 0.0209, "Noroeste": 0.0204, "Cuyo": 0.0205, "Patagonia": 0.0179}, Cobertura.MEDIDA_SEPA),
    Item("05.6.2", "Servicios domésticos y para el hogar", "clase", '05.6', {"GBA": 0.0199, "Pampeana": 0.0169, "Noreste": 0.0147, "Noroeste": 0.0166, "Cuyo": 0.0164, "Patagonia": 0.0123}, Cobertura.NO_SCRAPEABLE),
    Item("06", "Salud", "division", None, {"GBA": 0.088, "Pampeana": 0.0816, "Noreste": 0.0526, "Noroeste": 0.0633, "Cuyo": 0.074, "Patagonia": 0.0495}, Cobertura.PENDIENTE),
    Item("06.1", "Productos medicinales, artefactos y equipos para la salud", "grupo", '06', {"GBA": 0.0395, "Pampeana": 0.0476, "Noreste": 0.0338, "Noroeste": 0.0401, "Cuyo": 0.0498, "Patagonia": 0.0263}, Cobertura.PENDIENTE),
    Item("06.1.1", "Productos farmacéuticos", "clase", '06.1', {"GBA": 0.0353, "Pampeana": 0.0426, "Noreste": 0.0293, "Noroeste": 0.036, "Cuyo": 0.0455, "Patagonia": 0.0216}, Cobertura.MEDIDA_SEPA),
    Item("06.1.2", "Otros productos medicinales", "clase", '06.1', {"GBA": 0.0016, "Pampeana": 0.0018, "Noreste": 0.0021, "Noroeste": 0.0018, "Cuyo": 0.0018, "Patagonia": 0.0011}, Cobertura.MEDIDA_SEPA),
    Item("06.1.3", "Artefactos y equipos terapéuticos y sus reparaciones", "clase", '06.1', {"GBA": 0.0025, "Pampeana": 0.0031, "Noreste": 0.0024, "Noroeste": 0.0023, "Cuyo": 0.0024, "Patagonia": 0.0036}, Cobertura.PENDIENTE),
    Item("06.2", "Servicios para pacientes externos", "grupo", '06', {"GBA": 0.0168, "Pampeana": 0.0161, "Noreste": 0.0119, "Noroeste": 0.0157, "Cuyo": 0.0142, "Patagonia": 0.0149}, Cobertura.PENDIENTE),
    Item("06.2.1", "Servicios médicos para pacientes externos", "clase", '06.2', {"GBA": 0.0108, "Pampeana": 0.0085, "Noreste": 0.0049, "Noroeste": 0.0079, "Cuyo": 0.0091, "Patagonia": 0.0078}, Cobertura.PENDIENTE),
    Item("06.2.2", "Servicios y tratamientos odontológicos", "clase", '06.2', {"GBA": 0.0046, "Pampeana": 0.0048, "Noreste": 0.005, "Noroeste": 0.0057, "Cuyo": 0.0024, "Patagonia": 0.0049}, Cobertura.PENDIENTE),
    Item("06.2.3", "Servicios auxiliares para pacientes externos", "clase", '06.2', {"GBA": 0.0014, "Pampeana": 0.0028, "Noreste": 0.0019, "Noroeste": 0.0021, "Cuyo": 0.0027, "Patagonia": 0.0023}, Cobertura.PENDIENTE),
    Item("06.4", "Gastos de prepagas y obras sociales", "grupo", '06', {"GBA": 0.0318, "Pampeana": 0.0179, "Noreste": 0.007, "Noroeste": 0.0075, "Cuyo": 0.01, "Patagonia": 0.0082}, Cobertura.PENDIENTE),
    Item("07", "Transporte", "division", None, {"GBA": 0.1159, "Pampeana": 0.1041, "Noreste": 0.0963, "Noroeste": 0.0841, "Cuyo": 0.121, "Patagonia": 0.1342}, Cobertura.PENDIENTE),
    Item("07.1", "Adquisición de vehículos", "grupo", '07', {"GBA": 0.0248, "Pampeana": 0.0289, "Noreste": 0.0276, "Noroeste": 0.0158, "Cuyo": 0.0295, "Patagonia": 0.0492}, Cobertura.PENDIENTE),
    Item("07.1.1", "Vehículos a motor", "clase", '07.1', {"GBA": 0.0245, "Pampeana": 0.0271, "Noreste": 0.0235, "Noroeste": 0.0135, "Cuyo": 0.0284, "Patagonia": 0.0477}, Cobertura.PENDIENTE),
    Item("07.1.2", "Motocicletas", "clase", '07.1', {"GBA": 0.0002, "Pampeana": 0.0015, "Noreste": 0.0033, "Noroeste": 0.0018, "Cuyo": 0.0009, "Patagonia": 0.0008}, Cobertura.PENDIENTE),
    Item("07.1.3", "Bicicletas", "clase", '07.1', {"GBA": 0.0001, "Pampeana": 0.0003, "Noreste": 0.0008, "Noroeste": 0.0005, "Cuyo": 0.0003, "Patagonia": 0.0007}, Cobertura.PENDIENTE),
    Item("07.2", "Funcionamiento de equipos de transporte personal", "grupo", '07', {"GBA": 0.0508, "Pampeana": 0.0554, "Noreste": 0.0491, "Noroeste": 0.0448, "Cuyo": 0.069, "Patagonia": 0.0607}, Cobertura.PENDIENTE),
    Item("07.2.1", "Funcionamiento de equipos de transporte de uso del hogar", "clase", '07.2', {"GBA": 0.0056, "Pampeana": 0.0052, "Noreste": 0.0041, "Noroeste": 0.0041, "Cuyo": 0.0087, "Patagonia": 0.0066}, Cobertura.PENDIENTE),
    Item("07.2.2", "Combustibles y lubricantes para vehículos de uso del hogar", "clase", '07.2', {"GBA": 0.0378, "Pampeana": 0.0459, "Noreste": 0.0426, "Noroeste": 0.038, "Cuyo": 0.0563, "Patagonia": 0.0512}, Cobertura.PENDIENTE),
    Item("07.2.3", "Conservación y reparación de vehículos de uso del hogar", "clase", '07.2', {"GBA": 0.0015, "Pampeana": 0.0014, "Noreste": 0.001, "Noroeste": 0.0007, "Cuyo": 0.0022, "Patagonia": 0.0016}, Cobertura.PENDIENTE),
    Item("07.2.4", "Servicios relativos a los vehículos de uso del hogar", "clase", '07.2', {"GBA": 0.0059, "Pampeana": 0.0029, "Noreste": 0.0015, "Noroeste": 0.002, "Cuyo": 0.0018, "Patagonia": 0.0013}, Cobertura.PENDIENTE),
    Item("07.3", "Transporte público", "grupo", '07', {"GBA": 0.0402, "Pampeana": 0.0198, "Noreste": 0.0196, "Noroeste": 0.0235, "Cuyo": 0.0225, "Patagonia": 0.0244}, Cobertura.PENDIENTE),
    # 07.3.1 SOLO tiene peso en GBA segun la fuente oficial
    # (ponderadores_ipc.xls): el resto de las regiones viene en blanco,
    # consistente con que el transporte ferroviario de pasajeros es
    # practicamente exclusivo del AMBA. Declarado en 0% en las demas
    # regiones, no omitido, para que quede explicito que es una lectura
    # correcta de la fuente y no un hueco de carga.
    Item("07.3.1", "Servicios de transporte ferroviario", "clase", '07.3', {"GBA": 0.004, "Pampeana": 0.0, "Noreste": 0.0, "Noroeste": 0.0, "Cuyo": 0.0, "Patagonia": 0.0}, Cobertura.PENDIENTE),
    Item("07.3.2", "Servicios de transporte automotor", "clase", '07.3', {"GBA": 0.0332, "Pampeana": 0.0193, "Noreste": 0.0191, "Noroeste": 0.0233, "Cuyo": 0.021, "Patagonia": 0.0217}, Cobertura.PENDIENTE),
    Item("07.3.3", "Servicios de transporte aéreo", "clase", '07.3', {"GBA": 0.0026, "Pampeana": 0.0003, "Noreste": 0.0002, "Noroeste": 0.0001, "Cuyo": 0.0011, "Patagonia": 0.0021}, Cobertura.PENDIENTE),
    Item("07.3.6", "Otros servicios de transporte", "clase", '07.3', {"GBA": 0.0004, "Pampeana": 0.0002, "Noreste": 0.0002, "Noroeste": 0.0001, "Cuyo": 0.0005, "Patagonia": 0.0006}, Cobertura.PENDIENTE),
    Item("08", "Comunicación", "division", None, {"GBA": 0.0281, "Pampeana": 0.0286, "Noreste": 0.0282, "Noroeste": 0.0259, "Cuyo": 0.0253, "Patagonia": 0.0319}, Cobertura.PENDIENTE),
    Item("08.1.1", "Servicios postales", "clase", '08.1', {"GBA": 0.0002, "Pampeana": 0.0002, "Noreste": 0.0003, "Noroeste": 0.0003, "Cuyo": 0.0002, "Patagonia": 0.0003}, Cobertura.PENDIENTE),
    Item("08.2", "Equipos telefónicos", "grupo", '08', {"GBA": 0.0008, "Pampeana": 0.0005, "Noreste": 0.0005, "Noroeste": 0.0008, "Cuyo": 0.0007, "Patagonia": 0.0003}, Cobertura.PENDIENTE),
    Item("08.2.1", "Equipos teléfonicos fijos", "clase", '08.2', {"GBA": 0.0002, "Pampeana": 0.0, "Noreste": 0.0, "Noroeste": 0.0, "Cuyo": 0.0, "Patagonia": 0.0}, Cobertura.PENDIENTE),
    Item("08.2.2", "Equipos telefonicos móviles", "clase", '08.2', {"GBA": 0.0006, "Pampeana": 0.0005, "Noreste": 0.0005, "Noroeste": 0.0008, "Cuyo": 0.0006, "Patagonia": 0.0002}, Cobertura.PENDIENTE),
    Item("08.3", "Servicios de telefonía e internet", "grupo", '08', {"GBA": 0.0272, "Pampeana": 0.0279, "Noreste": 0.0274, "Noroeste": 0.0248, "Cuyo": 0.0245, "Patagonia": 0.0313}, Cobertura.PENDIENTE),
    Item("08.3.1", "Servicio de teléfonos fijos", "clase", '08.3', {"GBA": 0.0058, "Pampeana": 0.0061, "Noreste": 0.006, "Noroeste": 0.0053, "Cuyo": 0.0054, "Patagonia": 0.0067}, Cobertura.PENDIENTE),
    Item("08.3.2", "Servicio de telefonía móvil", "clase", '08.3', {"GBA": 0.0139, "Pampeana": 0.0147, "Noreste": 0.0143, "Noroeste": 0.0128, "Cuyo": 0.0131, "Patagonia": 0.0161}, Cobertura.PENDIENTE),
    Item("08.3.3", "Servicio de conexión a internet", "clase", '08.3', {"GBA": 0.0076, "Pampeana": 0.0071, "Noreste": 0.0071, "Noroeste": 0.0067, "Cuyo": 0.006, "Patagonia": 0.0085}, Cobertura.PENDIENTE),
    Item("09", "Recreación y cultura", "division", None, {"GBA": 0.0746, "Pampeana": 0.0739, "Noreste": 0.0623, "Noroeste": 0.0595, "Cuyo": 0.0672, "Patagonia": 0.0777}, Cobertura.PENDIENTE),
    Item("09.1", "Equipos audiovisuales, fotográficos y de procesamiento de la información", "grupo", '09', {"GBA": 0.0134, "Pampeana": 0.0119, "Noreste": 0.0134, "Noroeste": 0.0106, "Cuyo": 0.0108, "Patagonia": 0.0172}, Cobertura.PENDIENTE),
    Item("09.1.1", "Equipo para la recepción, grabación y reproducción de sonidos e imágenes", "clase", '09.1', {"GBA": 0.0042, "Pampeana": 0.0046, "Noreste": 0.0083, "Noroeste": 0.0052, "Cuyo": 0.0047, "Patagonia": 0.0073}, Cobertura.PENDIENTE),
    Item("09.1.2", "Equipo fotográfico y cinematográfico e instrumentos ópticos", "clase", '09.1', {"GBA": 0.0019, "Pampeana": 0.0013, "Noreste": 0.0003, "Noroeste": 0.0005, "Cuyo": 0.0005, "Patagonia": 0.0019}, Cobertura.PENDIENTE),
    Item("09.1.3", "Equipos de procesamiento e información", "clase", '09.1', {"GBA": 0.0044, "Pampeana": 0.0039, "Noreste": 0.0033, "Noroeste": 0.0031, "Cuyo": 0.003, "Patagonia": 0.0051}, Cobertura.PENDIENTE),
    Item("09.1.4", "Medios para grabación", "clase", '09.1', {"GBA": 0.0029, "Pampeana": 0.0021, "Noreste": 0.0016, "Noroeste": 0.0018, "Cuyo": 0.0027, "Patagonia": 0.003}, Cobertura.PENDIENTE),
    Item("09.3", "Otros artículos para la recreación, jardines y animales", "grupo", '09', {"GBA": 0.0107, "Pampeana": 0.0097, "Noreste": 0.0059, "Noroeste": 0.0083, "Cuyo": 0.0114, "Patagonia": 0.0104}, Cobertura.PENDIENTE),
    Item("09.3.1", "Juegos, juguetes y hobbies", "clase", '09.3', {"GBA": 0.0036, "Pampeana": 0.004, "Noreste": 0.0027, "Noroeste": 0.0044, "Cuyo": 0.0044, "Patagonia": 0.0041}, Cobertura.MEDIDA_SEPA),
    Item("09.3.2", "Equipo para el deporte, campamento y recreación al aire libre", "clase", '09.3', {"GBA": 0.0007, "Pampeana": 0.0009, "Noreste": 0.0003, "Noroeste": 0.0004, "Cuyo": 0.0004, "Patagonia": 0.001}, Cobertura.PENDIENTE),
    Item("09.3.4", "Mascotas y productos conexos", "clase", '09.3', {"GBA": 0.0065, "Pampeana": 0.0048, "Noreste": 0.003, "Noroeste": 0.0036, "Cuyo": 0.0066, "Patagonia": 0.0053}, Cobertura.EXCLUIDA),
    Item("09.4", "Servicios recreativos y culturales", "grupo", '09', {"GBA": 0.0305, "Pampeana": 0.0288, "Noreste": 0.0228, "Noroeste": 0.0227, "Cuyo": 0.0268, "Patagonia": 0.0302}, Cobertura.PENDIENTE),
    Item("09.4.1", "Servicios recreativos y deportivos", "clase", '09.4', {"GBA": 0.0086, "Pampeana": 0.0047, "Noreste": 0.0037, "Noroeste": 0.004, "Cuyo": 0.0052, "Patagonia": 0.0042}, Cobertura.PENDIENTE),
    Item("09.4.2", "Servicios culturales", "clase", '09.4', {"GBA": 0.0219, "Pampeana": 0.0241, "Noreste": 0.019, "Noroeste": 0.0188, "Cuyo": 0.0216, "Patagonia": 0.0261}, Cobertura.PENDIENTE),
    Item("09.5", "Periódicos, diarios, revistas, libros y artículos de papelería", "grupo", '09', {"GBA": 0.0149, "Pampeana": 0.0162, "Noreste": 0.0184, "Noroeste": 0.0158, "Cuyo": 0.0152, "Patagonia": 0.0183}, Cobertura.PENDIENTE),
    Item("09.5.1", "Libros", "clase", '09.5', {"GBA": 0.0069, "Pampeana": 0.006, "Noreste": 0.0086, "Noroeste": 0.0064, "Cuyo": 0.008, "Patagonia": 0.0091}, Cobertura.PENDIENTE),
    Item("09.5.2", "Diarios y publicaciones periódicas", "clase", '09.5', {"GBA": 0.0051, "Pampeana": 0.0058, "Noreste": 0.005, "Noroeste": 0.0048, "Cuyo": 0.0041, "Patagonia": 0.0041}, Cobertura.PENDIENTE),
    Item("09.5.4", "Papel y útiles de oficina y materiales de dibujo", "clase", '09.5', {"GBA": 0.003, "Pampeana": 0.0044, "Noreste": 0.0048, "Noroeste": 0.0045, "Cuyo": 0.0031, "Patagonia": 0.0051}, Cobertura.PENDIENTE),
    Item("09.6", "Paquetes turísticos", "grupo", '09', {"GBA": 0.005, "Pampeana": 0.0074, "Noreste": 0.0018, "Noroeste": 0.0021, "Cuyo": 0.003, "Patagonia": 0.0016}, Cobertura.PENDIENTE),
    Item("10", "Educación", "division", None, {"GBA": 0.0302, "Pampeana": 0.0161, "Noreste": 0.0136, "Noroeste": 0.0204, "Cuyo": 0.0224, "Patagonia": 0.0209}, Cobertura.PENDIENTE),
    Item("10.1", "Educación preescolar y primaria", "grupo", '10', {"GBA": 0.013, "Pampeana": 0.0066, "Noreste": 0.0034, "Noroeste": 0.0089, "Cuyo": 0.007, "Patagonia": 0.0076}, Cobertura.NO_SCRAPEABLE),
    Item("10.2", "Educcaión secundaria", "grupo", '10', {"GBA": 0.0048, "Pampeana": 0.0015, "Noreste": 0.0014, "Noroeste": 0.003, "Cuyo": 0.002, "Patagonia": 0.0029}, Cobertura.NO_SCRAPEABLE),
    Item("10.3", "Educación postsecundaria, no terciaria", "grupo", '10', {"GBA": 0.0063, "Pampeana": 0.0038, "Noreste": 0.0052, "Noroeste": 0.0047, "Cuyo": 0.0092, "Patagonia": 0.0039}, Cobertura.PENDIENTE),
    Item("10.5", "Educación no atribuible a ningún nivel", "grupo", '10', {"GBA": 0.0061, "Pampeana": 0.0042, "Noreste": 0.0036, "Noroeste": 0.0039, "Cuyo": 0.0041, "Patagonia": 0.0065}, Cobertura.PENDIENTE),
    Item("11", "Restaurantes y hoteles", "division", None, {"GBA": 0.1084, "Pampeana": 0.081, "Noreste": 0.0496, "Noroeste": 0.0799, "Cuyo": 0.0685, "Patagonia": 0.0508}, Cobertura.PENDIENTE),
    Item("11.1", "Restaurantes y comidas fuera del hogar", "grupo", '11', {"GBA": 0.1031, "Pampeana": 0.0784, "Noreste": 0.0484, "Noroeste": 0.0782, "Cuyo": 0.0652, "Patagonia": 0.0491}, Cobertura.PENDIENTE),
    Item("11.2", "Hoteles", "grupo", '11', {"GBA": 0.0053, "Pampeana": 0.0026, "Noreste": 0.0011, "Noroeste": 0.0016, "Cuyo": 0.0032, "Patagonia": 0.0016}, Cobertura.PENDIENTE),
    Item("12", "Bienes y servicios varios", "division", None, {"GBA": 0.0355, "Pampeana": 0.0358, "Noreste": 0.033, "Noroeste": 0.034, "Cuyo": 0.0363, "Patagonia": 0.0314}, Cobertura.PENDIENTE),
    Item("12.1", "Cuidado personal", "grupo", '12', {"GBA": 0.0282, "Pampeana": 0.0307, "Noreste": 0.0307, "Noroeste": 0.0318, "Cuyo": 0.0311, "Patagonia": 0.0266}, Cobertura.PENDIENTE),
    Item("12.1.1", "Salones de peluquería y establecimientos de cuidados personal", "clase", '12.1', {"GBA": 0.0085, "Pampeana": 0.0067, "Noreste": 0.0055, "Noroeste": 0.0055, "Cuyo": 0.007, "Patagonia": 0.0053}, Cobertura.PENDIENTE),
    Item("12.1.3", "Otros aparatos, artículos y productos para la atención personal", "clase", '12.1', {"GBA": 0.0197, "Pampeana": 0.024, "Noreste": 0.0252, "Noroeste": 0.0263, "Cuyo": 0.024, "Patagonia": 0.0213}, Cobertura.MEDIDA_SEPA),
    Item("12.5", "Seguros", "grupo", '12', {"GBA": 0.0047, "Pampeana": 0.0032, "Noreste": 0.001, "Noroeste": 0.0008, "Cuyo": 0.0033, "Patagonia": 0.0035}, Cobertura.PENDIENTE),
    Item("12.7", "Otros servicios", "grupo", '12', {"GBA": 0.0026, "Pampeana": 0.0019, "Noreste": 0.0013, "Noroeste": 0.0014, "Cuyo": 0.0019, "Patagonia": 0.0013}, Cobertura.PENDIENTE),
]

CANASTA: dict[str, Item] = {it.codigo: it for it in ITEMS}


def divisiones() -> list[Item]:
    return [it for it in ITEMS if it.nivel == "division"]


def grupos_de_division(div_codigo: str) -> list[Item]:
    """Los grupos (nivel intermedio) de una división, en el orden en que
    aparecen en la tabla oficial. Necesario para la navegación de 3
    niveles división > grupo > clase que reemplazó al intento anterior
    de agregar un cuarto nivel (subclase) — el usuario señaló que INDEC
    no publica ponderadores oficiales por debajo de clase, así que
    subclase hubiera exigido inventar/estimar pesos sin fuente, cuando
    grupo y clase ya cubren perfecto lo que sí está confirmado
    (ver docs/coicop_notas_explicativas.md y la tabla de
    ponderadores_ipc.xls, verificada con 0 divergencias)."""
    return [it for it in ITEMS if it.nivel == "grupo" and it.padre == div_codigo]


def clases_de_grupo(grupo_codigo: str) -> list[Item]:
    """Las clases de un grupo específico — el tercer nivel de la
    navegación división > grupo > clase."""
    return [it for it in ITEMS if it.nivel == "clase" and it.padre == grupo_codigo]


def clases_de_division(div_codigo: str) -> list[Item]:
    grupos = [it.codigo for it in ITEMS if it.nivel == "grupo" and it.padre == div_codigo]
    return [it for it in ITEMS if it.nivel == "clase" and it.padre in grupos]


def pesos_de(nivel: str, region: str = "GBA", padre: str | None = None) -> dict:
    return {it.codigo: it.peso(region) for it in ITEMS
            if it.nivel == nivel and (padre is None or it.padre == padre)}


CLASES_CON_COBERTURA_SEPA = [it.codigo for it in ITEMS
                              if it.nivel == "clase" and it.cobertura == Cobertura.MEDIDA_SEPA]
CLASES_SIN_COBERTURA_SEPA = [it.codigo for it in ITEMS
                              if it.nivel == "clase" and it.cobertura != Cobertura.MEDIDA_SEPA]


# --- API de compatibilidad -----------------------------------------------
# `engine/nacional.py` usa estos nombres. Se exponen aca para tener un unico
# lugar donde vive la estructura de la canasta.
PESO_REGION_NACIONAL = PESO_REGION


def peso(codigo: str, region: str = "GBA") -> float:
    """Ponderador de un item de la canasta en una region dada.
    Devuelve 0.0 si el codigo no existe, para que un codigo mal escrito no
    rompa el calculo silenciosamente con un KeyError a mitad de camino."""
    item = CANASTA.get(codigo)
    return item.peso(region) if item else 0.0


def cobertura_estructural_division(div_codigo: str, region: str = "GBA") -> dict:
    """Para una division, descompone su peso oficial en tres partes que NO
    son lo mismo (ver el docstring completo en
    scripts/auditar_cobertura.py, que es quien usa esto):

      - "medido": subcategorias con dato real de SEPA.
      - "declarado_sin_medir": subcategorias conocidas (con peso oficial)
        pero sin fuente de datos todavia.
      - "sin_declarar": parte del peso oficial de la division para la que
        NO HAY NINGUNA subcategoria cargada — un hueco estructural (por
        ejemplo, el grupo "Tabaco" dentro de "Bebidas alcoholicas y
        tabaco" no tiene ninguna clase hija declarada todavia).

    Devuelve un diccionario con las tres fracciones (0.0 a 1.0, no %) mas
    "referencia" (el peso total usado como base del 100%)."""
    div = CANASTA[div_codigo]
    grupos = [cod for cod, item in CANASTA.items()
             if item.nivel == "grupo" and item.padre == div_codigo]
    peso_grupos = sum(CANASTA[g].peso(region) for g in grupos)
    peso_division_oficial = div.peso(region)

    clases = clases_de_division(div_codigo)
    medido = sum(c.peso(region) for c in clases if c.cobertura == Cobertura.MEDIDA_SEPA)
    declarado_sin_medir = sum(c.peso(region) for c in clases
                              if c.cobertura != Cobertura.MEDIDA_SEPA)

    referencia = max(peso_division_oficial, peso_grupos)
    sin_declarar = max(0.0, referencia - medido - declarado_sin_medir)

    return {
        "medido": medido,
        "declarado_sin_medir": declarado_sin_medir,
        "sin_declarar": sin_declarar,
        "referencia": referencia,
    }
