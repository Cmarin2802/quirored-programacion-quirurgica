"""Nombres geográficos de referencia; H1/H2/H3 siguen siendo códigos internos."""
SEDES = {'H1': {'id': 'H1', 'nombre': 'Clínica Ricardo Palma', 'sigla': 'RP', 'direccion': 'Av. Javier Prado Este 1066, San Isidro, Lima, Perú', 'fuente': 'https://preguntasfrecuentes.crp.com.pe/ubicaci%C3%B3n-de-la-cl%C3%ADnica', 'tipo': 'CLINICA_PRIVADA', 'datos_operativos': 'SIMULADOS'}, 'H2': {'id': 'H2', 'nombre': 'Clínica Javier Prado', 'sigla': 'JP', 'direccion': 'Av. Javier Prado Este 499, San Isidro, Lima, Perú', 'fuente': 'https://cjp.pe/contacto/', 'tipo': 'CLINICA_PRIVADA', 'datos_operativos': 'SIMULADOS'}, 'H3': {'id': 'H3', 'nombre': 'Clínica Limatambo', 'sigla': 'LI', 'direccion': 'Av. República de Panamá 3606, San Isidro, Lima, Perú', 'fuente': 'https://imagescdn.rimac.com/blteb037de98628eb08/69a1dee7e0cee65e0e39098c/Red_de_clinicas_afiliadas_2026_V2_%281%29.pdf', 'tipo': 'CLINICA_PRIVADA', 'datos_operativos': 'SIMULADOS'}}

def nombre_sede(codigo):
    return SEDES.get(codigo, {}).get('nombre', codigo or '')

def catalogo_publico():
    return list(SEDES.values())
