# Business Ops - Reportes comerciales para Clawksis

Este modulo agrega herramientas comerciales seguras para Clawksis. Permite generar reportes de ventas, analisis de clientes, analisis de productos, desempeno de vendedores y resumenes ejecutivos a partir de un archivo CSV.

Las herramientas se ejecutan localmente desde el repositorio. No requieren sudo, no instalan paquetes y no acceden a secretos, tokens, llaves privadas ni archivos .env.

## Estado de validacion

Estas capacidades fueron probadas desde la interfaz de Clawksis usando:

    ./business_ops/clawksis-demo

La prueba confirmo:

    CLAWKSIS_BUSINESS_DEMO_STATUS=ok
    report_ejecutivo=ok
    report_semanal=ok
    report_clientes=ok
    report_productos=ok
    report_vendedores=ok

Tambien pasaron las validaciones del proyecto:

    QUALITY_GATE_STATUS=OK
    SECURITY_AUDIT_STATUS=OK
    15 tests OK

## Herramientas incluidas

### weekly-sales-report

Genera un reporte semanal de ventas.

Uso:

    ./business_ops/weekly-sales-report --input business_ops/examples/sample_sales.csv --markdown

### customer-insights

Analiza clientes, clientes principales, concentracion de ventas y oportunidades de seguimiento.

Uso:

    ./business_ops/customer-insights --input business_ops/examples/sample_sales.csv --markdown

### product-performance

Analiza desempeno de productos, productos lideres, baja participacion y dependencia comercial.

Uso:

    ./business_ops/product-performance --input business_ops/examples/sample_sales.csv --markdown

### sales-rep-performance

Analiza desempeno de vendedores, ventas netas, ordenes, ticket promedio y concentracion comercial.

Uso:

    ./business_ops/sales-rep-performance --input business_ops/examples/sample_sales.csv --markdown

### executive-summary

Genera un resumen ejecutivo comercial combinando ventas, clientes, productos y vendedores.

Uso:

    ./business_ops/executive-summary --input business_ops/examples/sample_sales.csv --markdown

## Comando corto en espanol

Para facilitar el uso desde Clawksis se agrego:

    ./business_ops/ventas

Ejemplos:

    ./business_ops/ventas --tipo ejecutivo
    ./business_ops/ventas --tipo semanal
    ./business_ops/ventas --tipo clientes
    ./business_ops/ventas --tipo productos
    ./business_ops/ventas --tipo vendedores

## Comando recomendado para interfaz conversacional

Para respuestas rapidas en Clawksis se recomienda:

    ./business_ops/ventas-resumen

Este comando devuelve una salida compacta para que la IA pueda leerla y explicarla.

Salida esperada:

    VENTAS_RESUMEN_STATUS=ok
    periodo=2026-06-01 a 2026-06-07
    ventas_netas=1,610,000
    ordenes=8
    clientes=8
    ticket_promedio=201,250
    producto_lider=Plan Empresarial (680,000)
    region_lider=Bogota (1,030,000)
    vendedor_lider=Laura (1,030,000)
    cliente_principal=Cliente H (450,000)

## Prueba integral

Para validar todas las capacidades comerciales:

    ./business_ops/clawksis-demo

Debe terminar con:

    CLAWKSIS_BUSINESS_DEMO_STATUS=ok

## Formato esperado del CSV

El archivo de entrada debe tener estas columnas:

    date,order_id,customer,product,quantity,unit_price,discount,region,sales_rep

Ejemplo:

    date,order_id,customer,product,quantity,unit_price,discount,region,sales_rep
    2026-06-01,ORD-001,Cliente A,Plan Premium,2,120000,10000,Bogota,Laura

## Uso con lenguaje natural

Estas herramientas pueden usarse con lenguaje natural si Clawksis tiene acceso a la terminal del repositorio.

Ejemplo:

    Hazme un resumen ejecutivo comercial.

Comando recomendado:

    ./business_ops/ventas-resumen

Ejemplo:

    Realiza un reporte semanal de ventas.

Comando recomendado:

    ./business_ops/ventas --tipo semanal --input business_ops/examples/sample_sales.csv --markdown

Ejemplo:

    Analiza cuales clientes deberian recibir seguimiento.

Comando recomendado:

    ./business_ops/ventas --tipo clientes --input business_ops/examples/sample_sales.csv --markdown

Ejemplo:

    Analiza que productos deberia impulsar el negocio.

Comando recomendado:

    ./business_ops/ventas --tipo productos --input business_ops/examples/sample_sales.csv --markdown

Ejemplo:

    Evalua el desempeno de los vendedores.

Comando recomendado:

    ./business_ops/ventas --tipo vendedores --input business_ops/examples/sample_sales.csv --markdown

## Compatibilidad con IA

Estas herramientas no dependen de un modelo especifico.

Pueden usarse con:

- Clawksis usando Ollama.
- Clawksis usando Claude.
- Otro proveedor de IA compatible con ejecucion de herramientas.
- Scripts locales o pruebas automatizadas.

La IA interpreta la solicitud y explica el resultado. Los calculos reales los hacen los scripts de business_ops. Esto reduce el riesgo de que la IA invente numeros.

Claude es compatible con estas mejoras siempre que Clawksis tenga habilitada la ejecucion de herramientas o terminal. De hecho, Claude puede ser una buena opcion para interpretar lenguaje natural y decidir que comando ejecutar.

## Reglas de seguridad

- No usar sudo.
- No instalar paquetes.
- No acceder a tokens, credenciales, llaves SSH ni archivos .env.
- No modificar archivos salvo que el usuario pida guardar o exportar un reporte.
- Usar ventas-resumen para respuestas conversacionales.
- Usar clawksis-demo para validar funcionamiento completo.

## Validacion recomendada

Antes de hacer commit o push:

    ./business_ops/clawksis-demo
    ./local_ops/quality-gate

Resultado esperado:

    CLAWKSIS_BUSINESS_DEMO_STATUS=ok
    QUALITY_GATE_STATUS=OK
