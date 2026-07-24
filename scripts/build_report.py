#!/usr/bin/env python3
"""Build and visually inspectable Phase 1 PDF report."""

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "phase1_project_report.pdf"
EVIDENCE_DIR = ROOT / "docs" / "evidence"
PAGE_WIDTH, PAGE_HEIGHT = A4
NAVY = colors.HexColor("#14213D")
BLUE = colors.HexColor("#2563EB")
CYAN = colors.HexColor("#0891B2")
PALE = colors.HexColor("#EFF6FF")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5B6475")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#B45309")
LIGHT_BORDER = colors.HexColor("#D8DEE9")


class ArchitectureDiagram(Flowable):
    def __init__(self, width=170 * mm, height=62 * mm):
        super().__init__()
        self.width = width
        self.height = height

    def draw_box(self, canvas, x, y, w, h, title, subtitle, fill):
        canvas.setFillColor(fill)
        canvas.setStrokeColor(LIGHT_BORDER)
        canvas.roundRect(x, y, w, h, 5, fill=1, stroke=1)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawCentredString(x + w / 2, y + h - 12, title)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(x + w / 2, y + 8, subtitle)

    def arrow(self, canvas, x1, y1, x2, y2):
        canvas.setStrokeColor(BLUE)
        canvas.setFillColor(BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(x1, y1, x2, y2)
        canvas.line(x2, y2, x2 - 4, y2 + 3)
        canvas.line(x2, y2, x2 - 4, y2 - 3)

    def draw(self):
        c = self.canv
        self.draw_box(c, 0, 38 * mm, 28 * mm, 16 * mm, "Traffic", "Python generator", PALE)
        self.draw_box(c, 38 * mm, 38 * mm, 32 * mm, 16 * mm, "Nginx", "gateway :8080", colors.HexColor("#DBEAFE"))
        self.draw_box(c, 82 * mm, 58 * mm, 34 * mm, 15 * mm, "Match", "/api/matches", colors.white)
        self.draw_box(c, 82 * mm, 38 * mm, 34 * mm, 15 * mm, "Team", "/api/teams", colors.white)
        self.draw_box(c, 82 * mm, 18 * mm, 34 * mm, 15 * mm, "Stadium", "/api/stadiums", colors.white)
        self.draw_box(c, 128 * mm, 38 * mm, 38 * mm, 16 * mm, "JSONL logs", "gateway + services", colors.HexColor("#ECFEFF"))
        self.draw_box(c, 128 * mm, 5 * mm, 38 * mm, 19 * mm, "MapReduce", "Jobs 1 -> 5", colors.HexColor("#DCFCE7"))
        self.arrow(c, 28 * mm, 46 * mm, 38 * mm, 46 * mm)
        self.arrow(c, 70 * mm, 46 * mm, 82 * mm, 65.5 * mm)
        self.arrow(c, 70 * mm, 46 * mm, 82 * mm, 45.5 * mm)
        self.arrow(c, 70 * mm, 46 * mm, 82 * mm, 25.5 * mm)
        self.arrow(c, 116 * mm, 46 * mm, 128 * mm, 46 * mm)
        self.arrow(c, 147 * mm, 38 * mm, 147 * mm, 24 * mm)


def styles():
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=31,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=8 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=sample["Normal"],
            fontSize=12,
            leading=18,
            textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=BLUE,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.3,
            leading=14,
            textColor=INK,
            spaceAfter=2.2 * mm,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=sample["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=10,
            textColor=INK,
            backColor=colors.HexColor("#F4F6F8"),
            borderColor=LIGHT_BORDER,
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=2 * mm,
            spaceAfter=3 * mm,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=sample["Normal"],
            fontSize=9,
            leading=14,
            textColor=MUTED,
        ),
        "center": ParagraphStyle(
            "Center",
            parent=sample["Normal"],
            alignment=TA_CENTER,
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
    }


def header_footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(LIGHT_BORDER)
    canvas.line(20 * mm, PAGE_HEIGHT - 16 * mm, PAGE_WIDTH - 20 * mm, PAGE_HEIGHT - 16 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, PAGE_HEIGHT - 12 * mm, "WORLD CUP LOG ANALYTICS")
    canvas.drawRightString(PAGE_WIDTH - 20 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


def bullet(text, style):
    return Paragraph(f"<font color='#2563EB'>&#8226;</font> {text}", style)


def table(data, widths, header=True):
    header_cell = ParagraphStyle(
        "TableHeader",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    body_cell = ParagraphStyle(
        "TableBody",
        fontName="Helvetica",
        fontSize=7.8,
        leading=10,
        textColor=INK,
    )
    formatted = []
    for row_index, row in enumerate(data):
        cell_style = header_cell if header and row_index == 0 else body_cell
        formatted.append([Paragraph(str(cell), cell_style) for cell in row])
    result = Table(
        formatted,
        colWidths=widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    for row in range(1 if header else 0, len(data)):
        if row % 2 == 0:
            commands.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#F8FAFC")))
    result.setStyle(TableStyle(commands))
    return result


def evidence_story(style_map):
    story = [
        Paragraph("8. Live-run evidence", style_map["h1"]),
        Paragraph(
            "The assignment requires evidence from the genuine final Docker and "
            "Hadoop run. Available images are embedded below. A missing image is "
            "reported explicitly and must be captured before submission.",
            style_map["body"],
        ),
    ]
    evidence = (
        ("01-containers.png", "Healthy application containers"),
        ("02-nginx-request.png", "Successful request through Nginx"),
        ("03-nginx-log.png", "Correlated Nginx gateway record"),
        ("04-service-log.png", "Correlated backend service record"),
        ("05-traffic-generator.png", "100,000-request traffic summary"),
        ("06-hadoop-streaming.png", "Five successful Hadoop Streaming jobs"),
        ("07-intermediate-output.png", "Representative intermediate CSV output"),
        ("08-final-summary.png", "Final summary.json"),
    )
    for index, (filename, caption) in enumerate(evidence):
        if index == 4:
            story.append(PageBreak())
        path = EVIDENCE_DIR / filename
        story.append(Paragraph(caption, style_map["h2"]))
        if path.is_file():
            image = Image(str(path))
            max_width, max_height = 165 * mm, 95 * mm
            scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            story.extend([image, Spacer(1, 3 * mm)])
        else:
            missing = Table(
                [[Paragraph(f"Pending live evidence: {filename}", style_map["center"])]],
                colWidths=[165 * mm],
                rowHeights=[18 * mm],
            )
            missing.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#FDBA74")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.extend([missing, Spacer(1, 2 * mm)])
    return story


def build_story():
    s = styles()
    story = [
        Spacer(1, 27 * mm),
        Paragraph("World Cup Log Analytics", s["title"]),
        Paragraph(
            "Nginx API Gateway and Hadoop Streaming MapReduce<br/>"
            "Cloud Computing Final Project - Phase 1",
            s["subtitle"],
        ),
        Spacer(1, 18 * mm),
        ArchitectureDiagram(),
        Spacer(1, 22 * mm),
        Paragraph(
            "<b>Implementation:</b> mandatory Phase 1 pipeline<br/>"
            "<b>Team identification:</b> not supplied in this workspace<br/>"
            "<b>Report status:</b> implementation documented; live evidence pending Docker run",
            s["cover_meta"],
        ),
        PageBreak(),
        Paragraph("1. Executive summary", s["h1"]),
        Paragraph(
            "The system provides three containerized FastAPI services for World "
            "Cup match, team, and stadium data. Nginx is the only public entry "
            "point. It routes requests, forwards correlation headers, and writes "
            "a structured gateway log. Each backend writes a correlated, "
            "entity-aware service log. Five Hadoop Streaming jobs transform the "
            "logs into required CSV statistics and a final JSON summary.",
            s["body"],
        ),
        Paragraph("Scope and current verification", s["h2"]),
        bullet("All mandatory source code, configuration, and automation are implemented.", s["body"]),
        bullet("The deterministic end-to-end fixture validates calculations and tie-breaking.", s["body"]),
        bullet("The local suite currently contains 55 passing tests.", s["body"]),
        bullet("The genuine 100,000-request data run remains pending on a Docker-capable machine.", s["body"]),
        Paragraph("2. System architecture", s["h1"]),
        ArchitectureDiagram(),
        Paragraph(
            "The root Compose project creates one private bridge network. Nginx "
            "publishes host port 8080; backends expose port 8000 only inside the "
            "network. Persistent host mounts retain gateway and service logs. A "
            "separate Hadoop Compose project mounts the repository at /project "
            "inside the NameNode so the pipeline can access source logs and write "
            "host-visible outputs.",
            s["body"],
        ),
        table(
            [
                ["Component", "Responsibility", "Persistent artifact"],
                ["Nginx", "Route, default and forward headers, gateway timing", "data/nginx/nginx_access.log"],
                ["Backends", "Serve data and log entity-level outcomes", "data/service_logs/*.log"],
                ["Traffic generator", "Create varied, correlated load through Nginx", "No trace file"],
                ["Hadoop", "Execute five batch analytics stages", "outputs/job1..job4"],
                ["Final report job", "Combine analytics and prediction metadata", "outputs/final/summary.json"],
            ],
            [31 * mm, 79 * mm, 56 * mm],
        ),
        PageBreak(),
        Paragraph("3. API gateway and services", s["h1"]),
        table(
            [
                ["Route", "Backend", "Entity input", "Expected outcomes"],
                ["/api/matches", "match-service", "date", "200, 400, 404, forced 500"],
                ["/api/teams", "team-service", "name", "200, 404, forced 500"],
                ["/api/stadiums", "stadium-service", "name or city", "200, 400, 404, forced 500"],
            ],
            [34 * mm, 34 * mm, 35 * mm, 63 * mm],
        ),
        Paragraph("Header propagation", s["h2"]),
        Paragraph(
            "Nginx resolves effective request ID, country, and scenario values. "
            "Missing request IDs use Nginx's generated request identifier; country "
            "defaults to Unknown and scenario defaults to normal. The same effective "
            "values are logged at the gateway and forwarded to the backend, enabling "
            "request-level correlation.",
            s["body"],
        ),
        Paragraph(
            "curl -H \"X-Request-ID: manual-001\" \\\n"
            "  -H \"X-Client-Country: Iran\" \\\n"
            "  -H \"X-Scenario: normal\" \\\n"
            "  \"http://localhost:8080/api/teams?name=Argentina\"",
            s["code"],
        ),
        Paragraph("4. Structured logging", s["h1"]),
        Paragraph("Gateway schema", s["h2"]),
        Paragraph(
            "timestamp, request_id, client_ip, client_country, scenario, method, "
            "path, service, status_code, request_time_sec, user_agent",
            s["code"],
        ),
        Paragraph("Backend schema", s["h2"]),
        Paragraph(
            "timestamp, request_id, client_country, scenario, service, endpoint, "
            "entity_type, entity_value, status_code, processing_time_ms, event_type",
            s["code"],
        ),
        Paragraph(
            "Both schemas use one complete JSON object per line. Gateway time is a "
            "numeric string in seconds; service processing time is numeric "
            "milliseconds. The validator checks syntax, types, required fields, "
            "duplicate IDs, gateway/backend correlation, status agreement, service "
            "coverage, countries, scenarios, entity diversity, and timing diversity.",
            s["body"],
        ),
        PageBreak(),
        Paragraph("5. Traffic generation", s["h1"]),
        Paragraph(
            "The standard-library generator uses bounded concurrency, unique request "
            "IDs, deterministic seeds, timeouts, and an in-memory summary. A coverage "
            "prefix guarantees required services and scenarios before weighted random "
            "traffic creates intentionally uneven popularity. All requests target "
            "Nginx; no backend URL is accepted.",
            s["body"],
        ),
        Paragraph(
            "python traffic-generator/generate.py --requests 100000 \\\n"
            "  --nginx-url http://localhost:8080",
            s["code"],
        ),
        Paragraph("6. Hadoop Streaming design", s["h1"]),
        table(
            [
                ["Job", "Input", "Transformation", "Output"],
                ["1", "Raw gateway + service JSONL", "Validate, normalize, tag invalid rows", "3 CSV files"],
                ["2", "Clean gateway rows", "Service, endpoint, scenario metrics", "3 CSV files"],
                ["3", "Clean service rows", "Country/entity request counts", "3 CSV files"],
                ["4", "Job 3 counts", "Deterministic popular entity selection", "3 CSV files"],
                ["5", "Jobs 2-4 + predictions", "Cross-domain final aggregation", "summary.json"],
            ],
            [14 * mm, 42 * mm, 70 * mm, 39 * mm],
        ),
        Paragraph("Determinism and reruns", s["h2"]),
        Paragraph(
            "Each job uses one reducer. Composite keys are compact JSON arrays, and "
            "ties select the case-insensitive lexical minimum followed by original "
            "text order. The pipeline uses an isolated /phase1 HDFS namespace, "
            "deletes only known prior input and job-output paths, and materializes "
            "headers exactly once. A repeated local run produces byte-identical "
            "artifacts.",
            s["body"],
        ),
        PageBreak(),
        Paragraph("7. Testing and reproducibility", s["h1"]),
        table(
            [
                ["Test area", "Coverage"],
                ["Containers and Compose", "Images, health checks, mounts, private network, host ports"],
                ["Nginx", "Routes, upstreams, headers, JSONL fields, health and 404 responses"],
                ["Service logging", "Success, validation, not found, slow, forced errors, concurrent writes"],
                ["Traffic", "Gateway-only URLs, reproducibility, weighting, scenarios, concurrency"],
                ["Log validation", "Malformed rows, types, correlation, duplicates, diversity"],
                ["MapReduce", "Five-stage flow, malformed/empty input, metrics, ties, output schemas"],
                ["Final run", "Confirmation guard, preserved artifacts, cross-file summary consistency"],
            ],
            [49 * mm, 117 * mm],
        ),
        Paragraph(
            "python -m unittest discover -s tests -v\n"
            "python scripts/verify_local_e2e.py\n"
            "bash scripts/run_final_data.sh --confirm-final-run",
            s["code"],
        ),
        Paragraph("Clean-run safety", s["h2"]),
        Paragraph(
            "The application is stopped before log truncation. Only four known log "
            "paths are truncated in place, preventing deletion of an actively open "
            "Nginx file. The final workflow requires explicit confirmation and a "
            "request count of at least 100,000. The independent artifact verifier "
            "recomputes every final summary value from intermediate CSV files.",
            s["body"],
        ),
    ]
    story.extend(evidence_story(s))
    story.extend(
        [
            PageBreak(),
            Paragraph("9. Results interpretation", s["h1"]),
            Paragraph(
                "The final summary identifies traffic concentration, reliability, "
                "latency, and entity popularity. total_requests must equal cleaned "
                "gateway rows, cleaned service rows, and the sum of service totals. "
                "The highest error-rate service uses the Job 2 error ratio. The "
                "slowest endpoint uses average gateway response time. Overall entity "
                "fields sum Job 3 counts across countries, while popular_team_by_country "
                "comes from Job 4.",
                s["body"],
            ),
            Paragraph("Result availability", s["h2"]),
            Paragraph(
                "No final submission metrics are asserted in this draft because the "
                "Docker-based final run has not occurred in the current environment. "
                "After that run, rebuild this report so the live evidence and actual "
                "summary are included. This avoids presenting fixture data as real "
                "experimental evidence.",
                s["body"],
            ),
            Paragraph("10. Limitations and future work", s["h1"]),
            bullet("The mandatory implementation is batch-oriented; Spark Structured Streaming is optional and not implemented.", s["body"]),
            bullet("The supplied Hadoop image installs Python at startup and therefore needs package-repository access on a first clean run.", s["body"]),
            bullet("The report requires live evidence and team identification before submission.", s["body"]),
            Paragraph("11. Conclusion", s["h1"]),
            Paragraph(
                "The implementation establishes a reproducible path from API traffic "
                "to correlated structured logs, Hadoop Streaming analytics, and a "
                "cross-validated final report. Static contracts, unit tests, a "
                "hand-calculated end-to-end fixture, guarded execution, and final "
                "artifact checks reduce the risk of schema drift or inconsistent "
                "submission data. The remaining operational action is to run the "
                "workflow on Docker, capture evidence, and rebuild the PDF.",
                s["body"],
            ),
        ]
    )
    return story


def build_pdf(output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(
        20 * mm,
        17 * mm,
        PAGE_WIDTH - 40 * mm,
        PAGE_HEIGHT - 36 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=4 * mm,
        bottomPadding=0,
    )
    document = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        title="World Cup Log Analytics - Phase 1",
        author="Cloud Computing Project Team",
        subject="Nginx and Hadoop Streaming project report",
    )
    document.addPageTemplates(
        [PageTemplate(id="report", frames=[frame], onPage=header_footer)]
    )
    document.build(build_story())


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the Phase 1 PDF report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    build_pdf(args.output)
    print(f"created: {args.output}")
    missing = [
        name
        for name in (
            "01-containers.png",
            "02-nginx-request.png",
            "03-nginx-log.png",
            "04-service-log.png",
            "05-traffic-generator.png",
            "06-hadoop-streaming.png",
            "07-intermediate-output.png",
            "08-final-summary.png",
        )
        if not (EVIDENCE_DIR / name).is_file()
    ]
    if missing:
        print(f"draft report: {len(missing)} live evidence image(s) still missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
