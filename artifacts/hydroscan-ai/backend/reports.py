"""PDF report assembly from calculated analysis values and local visual assets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build_pdf_report(analysis: dict, analysis_dir: Path) -> Path:
    report_path = analysis_dir / "report.pdf"
    generation_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="HydroTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=28,
            textColor=colors.HexColor("#0f3742"),
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="HydroNote",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#51666b"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="HydroSection",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#0f766e"),
            spaceBefore=14,
            spaceAfter=7,
        )
    )
    document = SimpleDocTemplate(
        str(report_path),
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.58 * inch,
        title=f"HydroScan AI analysis {analysis['reportId']}",
        author="HydroScan AI",
    )
    story = [
        Paragraph("HydroScan AI", styles["HydroTitle"]),
        Paragraph("Satellite-derived environmental screening report", styles["Heading2"]),
        Spacer(1, 8),
        Paragraph(
            "<b>Interpretation boundary:</b> This report presents index-based candidate water regions and "
            "statistical spectral anomaly priorities. It does not certify water quality, pollution, or a "
            "verified river boundary.",
            styles["HydroNote"],
        ),
        Spacer(1, 9),
    ]
    metadata_rows = [
        ["Report ID", str(analysis["reportId"])],
        ["Generated", generation_time],
        ["Analysis ID", str(analysis["id"])],
        ["Study area label", str(analysis.get("areaLabel") or "Not specified")],
        ["Data mode", "Synthetic demonstration" if analysis["mode"] == "demonstration" else "User-uploaded raster bands"],
        ["Observation date", str(analysis.get("observationDate") or "Not supplied")],
        ["Source", str(analysis.get("sourceLabel") or "Not available")],
        ["Raster dimensions", f"{analysis['width']} × {analysis['height']} pixels"],
        ["CRS", str(analysis.get("crs") or "Not available; locations are in pixel coordinates")],
    ]
    metadata_table = Table(metadata_rows, colWidths=[1.45 * inch, 5.25 * inch])
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e7f2ef")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#143b43")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d4e1dd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([metadata_table, Paragraph("Calculated indicators", styles["HydroSection"])])
    metric_rows = [
        ["Indicator", "Calculated value", "Meaning"],
        ["NDWI threshold", f"{analysis['threshold']:.3f}", "Configured candidate-mask threshold"],
        ["Candidate water pixels", f"{analysis['candidateWaterPixels']:,}", "Cleaned NDWI candidate pixels"],
        ["Candidate coverage", f"{analysis['waterCoveragePercent']:.2f}%", "Candidate pixels / mutually valid pixels"],
        ["Valid pixel coverage", f"{analysis['validPixelPercent']:.2f}%", "Pixels usable across all four bands"],
        ["Water spectral anomalies", str(analysis["anomalyCount"]), "Outlier components inside candidate-water mask"],
    ]
    metric_table = Table(metric_rows, colWidths=[1.6 * inch, 1.25 * inch, 3.85 * inch], repeatRows=1)
    metric_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#143b43")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d4e1dd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8f6")]),
            ]
        )
    )
    story.extend(
        [
            metric_table,
            Spacer(1, 8),
            Paragraph(escape(analysis.get("dataQualityNote", "")), styles["HydroNote"]),
            Paragraph("Thresholds and methods", styles["HydroSection"]),
            Paragraph(escape(analysis.get("thresholdMethod", {}).get("mask", "")), styles["BodyText"]),
            Paragraph(escape(analysis.get("thresholdMethod", {}).get("cleaning", "")), styles["BodyText"]),
            Paragraph(escape(analysis.get("thresholdMethod", {}).get("anomalies", "")), styles["BodyText"]),
            Paragraph(escape(analysis.get("thresholdMethod", {}).get("priority", "")), styles["BodyText"]),
        ]
    )

    for asset, caption in (
        ("rgb.png", "RGB composite"),
        ("ndwi.png", "NDWI visualization"),
        ("comparison.png", "Raw and cleaned candidate-mask comparison"),
    ):
        image_path = analysis_dir / "assets" / asset
        if image_path.is_file():
            story.extend(
                [
                    Paragraph(caption, styles["HydroSection"]),
                    Image(str(image_path), width=6.25 * inch, height=3.65 * inch, kind="proportional"),
                ]
            )
    story.append(PageBreak())
    story.append(Paragraph("Potential pollution screening queue", styles["HydroSection"]))
    story.append(
        Paragraph(
            "Water-only spectral anomalies are sorted by mean robust outlier score. These are review candidates, not confirmed pollution. Coordinates are shown only when "
            "the uploaded raster has a usable CRS and affine transform; otherwise row and column are provided.",
            styles["HydroNote"],
        )
    )
    anomaly_rows = [["Region", "Priority", "Score", "Pixels", "Location", "Reason"]]
    for region in analysis.get("anomalies", []):
        if region.get("locationType") == "geographic" and region.get("coordinates"):
            latitude, longitude = region["coordinates"]
            location = f"{latitude:.5f}, {longitude:.5f}"
        else:
            location = f"row {region['row']}, col {region['column']}"
        anomaly_rows.append(
            [
                region["id"],
                region["priority"].title(),
                f"{region['score']:.2f}",
                f"{region['pixels']:,}",
                location,
                Paragraph(escape(region["explanation"]), styles["HydroNote"]),
            ]
        )
    if len(anomaly_rows) == 1:
        anomaly_rows.append(["—", "None", "—", "—", "—", "No regions met the configured outlier threshold."])
    anomaly_table = Table(
        anomaly_rows,
        colWidths=[0.55 * inch, 0.72 * inch, 0.55 * inch, 0.6 * inch, 1.1 * inch, 3.1 * inch],
        repeatRows=1,
    )
    anomaly_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#143b43")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d4e1dd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([anomaly_table, Paragraph("Limitations and follow-up", styles["HydroSection"])])
    for limitation in analysis.get("limitations", []):
        story.append(Paragraph(f"- {escape(limitation)}", styles["HydroNote"]))
    story.append(Spacer(1, 7))
    story.append(
        Paragraph(
            "Suggested follow-up: inspect candidate-water spectral anomalies against cloud-masked imagery, compare additional "
            "consistent observation dates, and validate candidate locations with independent field or "
            "authoritative water-quality measurements before drawing environmental conclusions.",
            styles["HydroNote"],
        )
    )
    document.build(story)
    return report_path
