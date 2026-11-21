"""
Branded PDF Report Generator for Physics Wallah:
Generates a 1-page high-density academic and counselling diagnostic scorecard
using ReportLab, ready for instant student delivery or counsellor calls.
"""

import io
from typing import Any, Dict, List, Optional
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_student_diagnostic_pdf(
    student_info: Dict[str, Any],
    eval_info: Dict[str, Any],
    matches: Dict[str, List[Dict[str, Any]]],
) -> io.BytesIO:
    """
    Constructs a 1-page A4 PDF scorecard containing student diagnostics,
    GATE score band, predicted AIR, and top matching IITs/NITs/PSUs.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()

    # Brand Colors
    c_primary = HexColor("#1E3A8A")  # Dark Blue
    c_accent = HexColor("#2563EB")   # Royal Blue
    c_dark = HexColor("#0F172A")     # Slate 900
    c_gray = HexColor("#475569")     # Slate 600
    c_light = HexColor("#F1F5F9")    # Slate 100
    c_white = HexColor("#FFFFFF")
    c_green = HexColor("#059669")
    c_amber = HexColor("#D97706")
    c_red = HexColor("#DC2626")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=c_primary,
    )

    sub_title_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=c_gray,
    )

    heading2_style = ParagraphStyle(
        "H2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=c_primary,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=c_dark,
    )

    metric_val_style = ParagraphStyle(
        "MetricVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        alignment=1,  # Center
        textColor=c_primary,
    )

    metric_label_style = ParagraphStyle(
        "MetricLbl",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        alignment=1,
        textColor=c_gray,
    )

    story = []

    # 1. Header Banner
    header_data = [
        [
            Paragraph("<b>PHYSICS WALLAH (PW)</b><br/><font size=7 color='#64748B'>KNOWLEDGE & COUNSELLING OPERATIONS</font>", title_style),
            Paragraph("<b>GATE ACADEMIC & COUNSELLING DIAGNOSTIC</b><br/><font size=7 color='#64748B'>OFFICIAL PREDICTOR REPORT</font>", ParagraphStyle("RightHeader", parent=title_style, alignment=2, fontSize=11, leading=14)),
        ]
    ]
    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 4))

    # Divider Line
    divider = Table([[""]], colWidths=[540], rowHeights=[2])
    divider.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c_accent)]))
    story.append(divider)
    story.append(Spacer(1, 8))

    # 2. Candidate Demographics Card
    cand_data = [
        [
            Paragraph("<b>Candidate:</b> " + str(student_info.get("name", "N/A")), body_style),
            Paragraph("<b>Mobile:</b> " + str(student_info.get("phone", "N/A")), body_style),
            Paragraph("<b>Category:</b> " + str(student_info.get("category", "GEN")), body_style),
        ],
        [
            Paragraph("<b>Paper:</b> GATE " + str(student_info.get("paper_code", "CS")), body_style),
            Paragraph("<b>Batch:</b> " + str(student_info.get("batch", "PW Student")), body_style),
            Paragraph("<b>NCL / PwD Status:</b> " + ("Valid" if student_info.get("has_valid_ncl", True) else "General"), body_style),
        ],
    ]
    cand_table = Table(cand_data, colWidths=[180, 180, 180])
    cand_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_light),
            ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(cand_table)
    story.append(Spacer(1, 10))

    # 3. Performance Metrics Box (5 columns)
    raw_score = eval_info.get("raw_score_total", 0.0)
    neg_lost = eval_info.get("marks_lost_to_negatives", 0.0)
    gate_score = eval_info.get("gate_score", 0)
    air_range = eval_info.get("air_range", "N/A")
    lead_class = eval_info.get("lead_classification", "NURTURE_REPEATER")

    perf_data = [
        [
            Paragraph(f"{raw_score:.2f}", metric_val_style),
            Paragraph(f"-{neg_lost:.2f}", ParagraphStyle("NegVal", parent=metric_val_style, textColor=c_red)),
            Paragraph(f"{gate_score}", metric_val_style),
            Paragraph(f"{air_range}", metric_val_style),
            Paragraph(f"{lead_class.replace('_', ' ')}", ParagraphStyle("LeadVal", parent=metric_val_style, fontSize=9, leading=11, textColor=c_green if "TOPPER" in lead_class or "IIT" in lead_class else c_amber)),
        ],
        [
            Paragraph("RAW SCORE (/100)", metric_label_style),
            Paragraph("MARKS LOST (NEGATIVE)", metric_label_style),
            Paragraph("PREDICTED GATE SCORE", metric_label_style),
            Paragraph("ESTIMATED AIR BAND", metric_label_style),
            Paragraph("COUNSELLOR PRIORITY", metric_label_style),
        ],
    ]
    perf_table = Table(perf_data, colWidths=[108, 108, 108, 108, 108])
    perf_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 1, c_accent),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(perf_table)
    story.append(Spacer(1, 10))

    # 4. College Recommendations: IITs (COAP) Table
    story.append(Paragraph("<b>Top IIT Opportunities (COAP Portal)</b>", heading2_style))
    story.append(Spacer(1, 3))

    coap_list = matches.get("coap_options", [])[:4]
    coap_rows = [["INSTITUTION", "PROGRAM", "ADMISSION MODE", "MATCH TIER"]]
    if coap_list:
        for opt in coap_list:
            coap_rows.append([
                opt.get("institution_name", ""),
                opt.get("program_name", ""),
                opt.get("admission_mode", "DIRECT_OFFER").replace("_", " "),
                opt.get("match_tier", "TARGET"),
            ])
    else:
        coap_rows.append(["No direct IIT options at current score tier", "Consider rank improvement", "-", "NURTURE"])

    coap_table = Table(coap_rows, colWidths=[160, 200, 100, 80])
    coap_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), c_primary),
            ("TEXTCOLOR", (0, 0), (-1, 0), c_white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [c_white, c_light]),
        ])
    )
    story.append(coap_table)
    story.append(Spacer(1, 8))

    # 5. College Recommendations: NITs (CCMT) Table
    story.append(Paragraph("<b>Top NIT / IIIT Opportunities (CCMT Portal)</b>", heading2_style))
    story.append(Spacer(1, 3))

    ccmt_list = matches.get("ccmt_options", [])[:4]
    ccmt_rows = [["INSTITUTION", "SPECIALIZATION", "ROUNDS", "MATCH TIER"]]
    if ccmt_list:
        for opt in ccmt_list:
            ccmt_rows.append([
                opt.get("institution_name", ""),
                opt.get("program_name", ""),
                "Rounds 1 - 3",
                opt.get("match_tier", "TARGET"),
            ])
    else:
        ccmt_rows.append(["Explore specialized state colleges or next session target", "-", "-", "NURTURE"])

    ccmt_table = Table(ccmt_rows, colWidths=[160, 200, 100, 80])
    ccmt_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#334155")),
            ("TEXTCOLOR", (0, 0), (-1, 0), c_white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [c_white, c_light]),
        ])
    )
    story.append(ccmt_table)
    story.append(Spacer(1, 8))

    # 6. PSU Recruitment Shortlist Table
    story.append(Paragraph("<b>Public Sector Undertakings (PSU) Placement Shortlist</b>", heading2_style))
    story.append(Spacer(1, 3))

    psu_list = matches.get("psu_options", [])[:3]
    psu_rows = [["PSU ORGANIZATION", "DESIGNATION POST", "ELIGIBILITY", "STATUS NOTE"]]
    if psu_list:
        for p in psu_list:
            psu_rows.append([
                p.get("psu_name", ""),
                p.get("post_name", ""),
                "ELIGIBLE" if p.get("is_eligible") else "DISQUALIFIED",
                (p.get("eligibility_note") or "")[:40],
            ])
    else:
        psu_rows.append(["No direct PSU shortlist at current rank band", "-", "INELIGIBLE", "PSUs typically require AIR < 300"])

    psu_table = Table(psu_rows, colWidths=[140, 160, 90, 150])
    psu_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0F766E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), c_white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [c_white, c_light]),
        ])
    )
    story.append(psu_table)
    story.append(Spacer(1, 10))

    # 7. Actionable Faculty Advice / Guidance Note
    advice_text = (
        "<b>PW Academic Strategy:</b> "
    )
    if gate_score >= 750:
        advice_text += "Strong contender for direct admission in top IITs and PSU interviews. Prioritize choice filling in COAP Round 1."
    elif gate_score >= 550:
        advice_text += "Focus on high-ROI interdisciplinary programs in older IITs and premier core specializations in NIT Trichy, Warangal, and Surathkal."
    else:
        advice_text += f"Noticeable score deduction of {neg_lost:.2f} marks to negative marking. Recommend targeted concept revision and test series practice with PW Dropper/Target Batches."

    advice_table = Table([[Paragraph(advice_text, body_style)]], colWidths=[540])
    advice_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FEF3C7")),
            ("BOX", (0, 0), (-1, -1), 1, HexColor("#F59E0B")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(advice_table)
    story.append(Spacer(1, 10))

    # 8. Footer
    footer_text = "<font size=6 color='#94A3B8'>CONFIDENTIAL • Generated by Physics Wallah In-House Admissions Engine • Predictor calculations based on multi-year weighted historical cutoffs and official GATE normalization methodology.</font>"
    story.append(Paragraph(footer_text, ParagraphStyle("Footer", parent=styles["Normal"], alignment=1)))

    doc.build(story)
    buffer.seek(0)
    return buffer
