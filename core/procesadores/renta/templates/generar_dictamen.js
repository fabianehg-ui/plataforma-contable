/**
 * Template del Dictamen Ejecutivo de Renta — recibe payload por stdin.
 *
 * Uso:
 *   echo '{"razon_social":"...","nit":"...",...}' | node generar_dictamen.js
 *
 * Payload esperado:
 * {
 *   razon_social: string,
 *   nit: string,
 *   ano_gravable: number,
 *   form110: { ...claves casillas... },
 *   conciliacion: {
 *     utilidad_contable_antes_impuestos: number,
 *     partidas_aumentan: [{codigo, nombre, valor, base_legal}, ...],
 *     partidas_disminuyen: [{...}],
 *     total_aumentos: number,
 *     total_disminuciones: number,
 *     renta_liquida_fiscal: number
 *   },
 *   retenciones: [{nombre, nit, concepto, base, retencion_106, autoret_105}, ...],
 *   plazo: string,
 *   fecha_generacion: string,
 *   ruta_salida: string
 * }
 */

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageNumber, PageBreak,
} = require('docx');

// Leer payload por stdin
let inputData = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => inputData += chunk);
process.stdin.on('end', () => {
  try {
    const payload = JSON.parse(inputData);
    generarDictamen(payload);
  } catch (e) {
    console.error('ERROR parseando payload:', e.message);
    process.exit(1);
  }
});

function generarDictamen(P) {
  const COLOR_PRIMARY = '1F4E78';
  const COLOR_ACCENT = '2E75B6';
  const COLOR_GRAY_LIGHT = 'F2F2F2';
  const COLOR_GRAY_MED = 'D9D9D9';
  const COLOR_OK = '006100';
  const COLOR_WARN = 'C00000';
  const COLOR_HEADER_FILL = '305496';
  const COLOR_HIGHLIGHT = 'FFF2CC';

  const fmt = (n) => n === 0 || n == null ? '-' : '$' + Math.round(n).toLocaleString('es-CO').replace(/,/g, '.');
  const f = P.form110 || {};
  const c = P.conciliacion || {};

  function p(text, opts = {}) {
    return new Paragraph({
      spacing: { before: opts.before || 0, after: opts.after || 100 },
      alignment: opts.align || AlignmentType.JUSTIFIED,
      children: [new TextRun({
        text, font: 'Arial', size: opts.size || 22,
        bold: opts.bold || false, italics: opts.italics || false,
        color: opts.color || '000000',
      })]
    });
  }

  function h1(text) {
    return new Paragraph({
      heading: HeadingLevel.HEADING_1,
      spacing: { before: 360, after: 180 },
      children: [new TextRun({ text, font: 'Arial', size: 32, bold: true, color: COLOR_PRIMARY })]
    });
  }
  function h3(text) {
    return new Paragraph({
      heading: HeadingLevel.HEADING_3,
      spacing: { before: 200, after: 100 },
      children: [new TextRun({ text, font: 'Arial', size: 22, bold: true, color: COLOR_ACCENT })]
    });
  }
  function bullet(text) {
    return new Paragraph({
      numbering: { reference: 'bullets', level: 0 },
      spacing: { after: 60 },
      children: [new TextRun({ text, font: 'Arial', size: 22 })]
    });
  }

  function cell(text, opts = {}) {
    return new TableCell({
      width: { size: opts.width || 2000, type: WidthType.DXA },
      borders: {
        top: { style: BorderStyle.SINGLE, size: 4, color: COLOR_GRAY_MED },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: COLOR_GRAY_MED },
        left: { style: BorderStyle.SINGLE, size: 4, color: COLOR_GRAY_MED },
        right: { style: BorderStyle.SINGLE, size: 4, color: COLOR_GRAY_MED },
      },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({
        alignment: opts.align || AlignmentType.LEFT,
        spacing: { before: 0, after: 0 },
        children: [new TextRun({
          text: String(text == null ? '' : text),
          font: 'Arial', size: opts.size || 20,
          bold: opts.bold || false,
          color: opts.color || '000000',
          italics: opts.italics || false,
        })]
      })]
    });
  }
  function headerCell(text, w) {
    return cell(text, { width: w, fill: COLOR_HEADER_FILL, color: 'FFFFFF',
                        bold: true, align: AlignmentType.CENTER, size: 20 });
  }
  function moneyCell(amount, opts = {}) {
    return cell(fmt(amount), { align: AlignmentType.RIGHT, ...opts });
  }

  // ===== PORTADA =====
  const portada = [
    new Paragraph({ spacing: { before: 1200 }, children: [new TextRun('')] }),
    new Paragraph({
      border: { bottom: { style: BorderStyle.SINGLE, size: 24, color: COLOR_PRIMARY, space: 1 } },
      spacing: { after: 240 }, children: [new TextRun('')]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 240 },
      children: [new TextRun({ text: 'DICTAMEN EJECUTIVO', font: 'Arial', size: 56, bold: true, color: COLOR_PRIMARY })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 600 },
      children: [new TextRun({ text: 'DECLARACIÓN DE RENTA Y COMPLEMENTARIO', font: 'Arial', size: 32, bold: true, color: COLOR_ACCENT })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 720 },
      children: [new TextRun({
        text: `Año Gravable ${P.ano_gravable}  \u2022  Formulario 110  \u2022  Persona Jurídica`,
        font: 'Arial', size: 26, italics: true,
      })]
    }),
    new Paragraph({
      border: {
        top: { style: BorderStyle.SINGLE, size: 12, color: COLOR_PRIMARY, space: 1 },
        bottom: { style: BorderStyle.SINGLE, size: 12, color: COLOR_PRIMARY, space: 1 },
      },
      spacing: { before: 120, after: 120 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: P.razon_social, font: 'Arial', size: 36, bold: true })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 60 },
      children: [new TextRun({ text: `NIT ${P.nit}`, font: 'Arial', size: 24 })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 60 },
      children: [new TextRun({ text: `Generado el ${P.fecha_generacion}`, font: 'Arial', size: 20, color: '666666' })]
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];

  // ===== RESUMEN EJECUTIVO =====
  const resumen = [
    h1('1. Resumen Ejecutivo'),
    p(`Este dictamen presenta el resultado de la liquidación de la Declaración de Renta del año gravable ${P.ano_gravable} para ${P.razon_social} (NIT ${P.nit}).`, { after: 200 }),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [5400, 3960],
      rows: [
        new TableRow({ tableHeader: true, children: [headerCell('Indicador', 5400), headerCell('Valor', 3960)] }),
        new TableRow({ children: [cell('Ingresos brutos', { width: 5400 }), moneyCell(f.casilla_58_total_ingresos_brutos, { width: 3960 })] }),
        new TableRow({ children: [cell('Costos y gastos deducibles', { width: 5400 }), moneyCell(f.casilla_67_total_costos_gastos_deducibles, { width: 3960 })] }),
        new TableRow({ children: [cell('Renta líquida gravable', { width: 5400, fill: COLOR_GRAY_LIGHT, bold: true }), moneyCell(f.casilla_79_renta_liquida_gravable, { width: 3960, fill: COLOR_GRAY_LIGHT, bold: true })] }),
        new TableRow({ children: [cell('Total impuesto a cargo', { width: 5400 }), moneyCell(f.casilla_99_total_impuesto_a_cargo, { width: 3960 })] }),
        new TableRow({ children: [cell('Total retenciones', { width: 5400 }), moneyCell(f.casilla_107_total_retenciones, { width: 3960 })] }),
        new TableRow({ children: [
          cell(f.casilla_114_total_saldo_a_favor > 0 ? 'SALDO A FAVOR' : 'SALDO A PAGAR',
              { width: 5400, fill: f.casilla_114_total_saldo_a_favor > 0 ? COLOR_OK : COLOR_WARN, bold: true, color: 'FFFFFF' }),
          moneyCell(f.casilla_114_total_saldo_a_favor > 0 ? f.casilla_114_total_saldo_a_favor : f.casilla_113_total_saldo_a_pagar,
              { width: 3960, fill: f.casilla_114_total_saldo_a_favor > 0 ? COLOR_OK : COLOR_WARN, bold: true, color: 'FFFFFF' })
        ]}),
      ]
    }),
  ];

  // ===== CONCILIACIÓN =====
  const conciliacionRows = [
    new TableRow({ tableHeader: true, children: [
      headerCell('Concepto', 4500), headerCell('Valor', 1860), headerCell('Base legal', 3000)
    ]}),
    new TableRow({ children: [
      cell('Utilidad contable antes de impuestos', { width: 4500, bold: true, fill: COLOR_HIGHLIGHT }),
      moneyCell(c.utilidad_contable_antes_impuestos, { width: 1860, bold: true, fill: COLOR_HIGHLIGHT }),
      cell('Estado de Resultados antes de provisión 5405', { width: 3000, fill: COLOR_HIGHLIGHT, italics: true })
    ]}),
    new TableRow({ children: [cell('(+) AUMENTAN LA RENTA',
      { width: 9360, fill: COLOR_ACCENT, color: 'FFFFFF', bold: true, align: AlignmentType.LEFT })] }),
    ...(c.partidas_aumentan || []).map(part => new TableRow({ children: [
      cell(part.nombre, { width: 4500 }),
      moneyCell(part.valor, { width: 1860 }),
      cell(part.base_legal || '', { width: 3000 })
    ]})),
    new TableRow({ children: [
      cell('TOTAL AUMENTOS', { width: 4500, bold: true, fill: COLOR_GRAY_LIGHT }),
      moneyCell(c.total_aumentos, { width: 1860, bold: true, fill: COLOR_GRAY_LIGHT }),
      cell('', { width: 3000, fill: COLOR_GRAY_LIGHT })
    ]}),
  ];
  if ((c.partidas_disminuyen || []).length > 0) {
    conciliacionRows.push(
      new TableRow({ children: [cell('(-) DISMINUYEN LA RENTA',
        { width: 9360, fill: COLOR_ACCENT, color: 'FFFFFF', bold: true, align: AlignmentType.LEFT })] }),
      ...c.partidas_disminuyen.map(part => new TableRow({ children: [
        cell(part.nombre, { width: 4500 }),
        moneyCell(part.valor, { width: 1860 }),
        cell(part.base_legal || '', { width: 3000 })
      ]})),
      new TableRow({ children: [
        cell('TOTAL DISMINUCIONES', { width: 4500, bold: true, fill: COLOR_GRAY_LIGHT }),
        moneyCell(c.total_disminuciones, { width: 1860, bold: true, fill: COLOR_GRAY_LIGHT }),
        cell('', { width: 3000, fill: COLOR_GRAY_LIGHT })
      ]}),
    );
  }
  conciliacionRows.push(new TableRow({ children: [
    cell('= RENTA LÍQUIDA FISCAL', { width: 4500, bold: true, fill: COLOR_PRIMARY, color: 'FFFFFF' }),
    moneyCell(c.renta_liquida_fiscal, { width: 1860, bold: true, fill: COLOR_PRIMARY, color: 'FFFFFF' }),
    cell('Casilla 72 del Form 110', { width: 3000, fill: COLOR_PRIMARY, color: 'FFFFFF' })
  ]}));

  const conciliacion = [
    h1('2. Conciliación Fiscal'),
    p('La conciliación fiscal toma la utilidad contable y le aplica las diferencias permanentes definidas en el Estatuto Tributario.', { after: 200 }),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [4500, 1860, 3000],
      rows: conciliacionRows
    }),
  ];

  // ===== LIQUIDACIÓN =====
  const liquidacion = [
    h1('3. Liquidación del Impuesto'),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [1200, 4800, 3360],
      rows: [
        new TableRow({ tableHeader: true, children: [
          headerCell('Casilla', 1200), headerCell('Concepto', 4800), headerCell('Valor', 3360)
        ]}),
        new TableRow({ children: [cell('79', { width: 1200, align: AlignmentType.CENTER }), cell('Renta líquida gravable', { width: 4800 }), moneyCell(f.casilla_79_renta_liquida_gravable, { width: 3360 })] }),
        new TableRow({ children: [cell('84', { width: 1200, align: AlignmentType.CENTER }), cell('Impuesto sobre rentas líquidas (35%)', { width: 4800 }), moneyCell(f.casilla_84_impuesto_rentas_liquidas || (f.casilla_99_total_impuesto_a_cargo), { width: 3360 })] }),
        new TableRow({ children: [cell('99', { width: 1200, align: AlignmentType.CENTER, bold: true, fill: COLOR_GRAY_LIGHT }), cell('TOTAL IMPUESTO A CARGO', { width: 4800, bold: true, fill: COLOR_GRAY_LIGHT }), moneyCell(f.casilla_99_total_impuesto_a_cargo, { width: 3360, bold: true, fill: COLOR_GRAY_LIGHT })] }),
        new TableRow({ children: [cell('107', { width: 1200, align: AlignmentType.CENTER }), cell('(-) Total retenciones', { width: 4800 }), moneyCell(f.casilla_107_total_retenciones, { width: 3360 })] }),
        new TableRow({ children: [cell('104', { width: 1200, align: AlignmentType.CENTER }), cell('(-) Saldo favor año anterior', { width: 4800 }), moneyCell(f.casilla_104_saldo_favor_anterior || 0, { width: 3360 })] }),
        new TableRow({ children: [cell('114', { width: 1200, align: AlignmentType.CENTER, bold: true, fill: COLOR_OK, color: 'FFFFFF' }), cell('TOTAL SALDO A FAVOR', { width: 4800, bold: true, fill: COLOR_OK, color: 'FFFFFF' }), moneyCell(f.casilla_114_total_saldo_a_favor, { width: 3360, bold: true, fill: COLOR_OK, color: 'FFFFFF' })] }),
      ]
    }),
  ];

  // ===== RETENCIONES (si hay detalle) =====
  const retenciones = [];
  if (P.retenciones && P.retenciones.length > 0) {
    retenciones.push(
      h1('4. Detalle de Retenciones'),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [600, 4200, 1800, 1100, 1660],
        rows: [
          new TableRow({ tableHeader: true, children: [
            headerCell('#', 600), headerCell('Agente retenedor', 4200),
            headerCell('NIT', 1800), headerCell('Concepto', 1100), headerCell('Retención', 1660)
          ]}),
          ...P.retenciones.map((r, i) => new TableRow({ children: [
            cell(i + 1, { width: 600, align: AlignmentType.CENTER }),
            cell(r.nombre, { width: 4200 }),
            cell(r.nit, { width: 1800, align: AlignmentType.CENTER, size: 18 }),
            cell(r.concepto, { width: 1100, align: AlignmentType.CENTER, size: 18 }),
            moneyCell((r.retencion_106 || 0) + (r.autoret_105 || 0), { width: 1660 }),
          ]})),
        ]
      }),
    );
  }

  // ===== HALLAZGOS Y PLAZO =====
  const hallazgos = [
    h1('5. Plazos y Recomendaciones'),
    h3('Plazo para presentar'),
    p(`Fecha límite: ${P.plazo}`, { after: 200, bold: true }),
    h3('Anexo obligatorio: Formato 2516'),
    p('La conciliación fiscal debe formalizarse en el Formato 2516 si los ingresos brutos fiscales superan 45.000 UVT.', { after: 200 }),
  ];

  // ===== CONCLUSIÓN =====
  const saldoFavor = f.casilla_114_total_saldo_a_favor || 0;
  const saldoPagar = f.casilla_113_total_saldo_a_pagar || 0;
  const conclusion = [
    h1('6. Conclusión'),
    p(`La declaración de renta del año gravable ${P.ano_gravable} de ${P.razon_social} arroja un ` +
      (saldoFavor > 0 ? `saldo a favor de ${fmt(saldoFavor)}.` : `saldo a pagar de ${fmt(saldoPagar)}.`),
      { after: 200 }),
    new Paragraph({
      border: {
        top: { style: BorderStyle.SINGLE, size: 12, color: COLOR_PRIMARY, space: 6 },
        bottom: { style: BorderStyle.SINGLE, size: 12, color: COLOR_PRIMARY, space: 6 },
      },
      spacing: { before: 200, after: 100 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: saldoFavor > 0 ? `Saldo a favor: ${fmt(saldoFavor)}` : `Saldo a pagar: ${fmt(saldoPagar)}`,
        font: 'Arial', size: 32, bold: true,
        color: saldoFavor > 0 ? COLOR_OK : COLOR_WARN,
      })]
    }),
  ];

  const styles = {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 32, bold: true, font: 'Arial', color: COLOR_PRIMARY },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, font: 'Arial', color: COLOR_ACCENT },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2 } },
    ]
  };

  const numbering = {
    config: [{
      reference: 'bullets',
      levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT,
                style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
    }]
  };

  const allChildren = [
    ...portada, ...resumen, ...conciliacion, ...liquidacion,
    ...retenciones, ...hallazgos, ...conclusion
  ];

  const doc = new Document({
    creator: 'Plataforma Tributaria',
    title: `Dictamen Renta AG ${P.ano_gravable} — ${P.razon_social}`,
    styles, numbering,
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({
              text: `Dictamen Renta AG ${P.ano_gravable} — ${P.razon_social}`,
              font: 'Arial', size: 18, color: '888888', italics: true,
            })],
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: COLOR_GRAY_MED, space: 4 } }
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: 'Página ', font: 'Arial', size: 18, color: '888888' }),
              new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 18, color: '888888' }),
              new TextRun({ text: ' de ', font: 'Arial', size: 18, color: '888888' }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Arial', size: 18, color: '888888' }),
            ]
          })]
        })
      },
      children: allChildren,
    }]
  });

  Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync(P.ruta_salida, buffer);
    console.log(`✓ Dictamen generado: ${P.ruta_salida}`);
  }).catch(err => {
    console.error('ERROR:', err);
    process.exit(1);
  });
}
