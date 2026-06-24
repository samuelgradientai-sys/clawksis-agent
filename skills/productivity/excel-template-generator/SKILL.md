---
name: excel-template-generator
description: "USE THIS to create professional Excel .xlsx templates and workbooks for business operations, inventory, sales, post-sale tracking, costs, customers, dashboards, and structured operational spreadsheets. Trigger on ES+EN: 'crear Excel', 'plantilla Excel', 'generar xlsx', 'crear plantilla de inventario', 'plantilla de ventas', 'plantilla postventa', 'spreadsheet template', 'Excel template', 'inventory workbook', 'sales workbook'."
argument-hint: 'excel-template-generator --template inventory|sales|postventa --output <file.xlsx>'
allowed-tools: Bash, Read, Write
author: Clawksis Gradient AI
license: MIT
user-invocable: true
metadata:
  clawksis:
    emoji: "📊"
  openclaw:
    emoji: "📊"
    requires:
      bins:
        - python3
---

# excel-template-generator — crear plantillas Excel profesionales

Esta skill crea archivos .xlsx seguros y editables para operaciones de negocio.

Usala cuando el usuario pida crear plantillas Excel, generar archivos .xlsx, crear formatos de inventario, ventas, clientes, costos, postventa o preparar hojas de seguimiento operativo.

## Seguridad

- No usa macros.
- No ejecuta fórmulas externas.
- No incluye tokens, API keys ni secretos.
- No sobrescribe archivos existentes salvo confirmación explícita.
- Guarda archivos en rutas explícitas o en ~/clawksis_exports/excel_templates/.
- Si se modifica un archivo existente, primero debe hacerse backup.

## Dependencia

Requiere openpyxl instalado en el entorno de Clawksis:

/opt/clawksis-agent/.venv/bin/python -m pip install "openpyxl==3.1.5"

## Plantillas disponibles

- inventory: inventario con SKU, producto, categoría, stock, costo, precio, margen, valor inventario y alerta de stock bajo.
- sales: ventas diarias con cliente, producto, cantidad, precio, descuento, total, método de pago, canal y estado.
- postventa: seguimiento postventa con cliente, caso, estado, prioridad, responsable, costo adicional y próxima acción.

## Uso

El script vive en:

scripts/generate_template.py

Ejemplo:

/opt/clawksis-agent/.venv/bin/python "$SKILL_DIR/scripts/generate_template.py" --template inventory --business-name "Clawksis" --output "$HOME/clawksis_exports/excel_templates/inventario.xlsx"
