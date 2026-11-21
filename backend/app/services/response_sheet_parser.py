"""
TCS iON Digialm Response Sheet Parser for GATE:
Extracts candidate information, question numbers, question IDs,
question types (MCQ/MSQ/NAT), chosen options, and entered numerical values
from candidate response sheets.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import httpx


@dataclass
class ParsedQuestion:
    question_number: int
    question_id: str
    question_type: str  # MCQ, MSQ, NAT
    status: str  # ATTEMPTED, SKIPPED
    chosen_options: Optional[List[str]] = None  # e.g., ["A"], ["A", "C"]
    given_answer: Optional[str] = None  # for NAT, e.g., "24.5"
    raw_status: Optional[str] = None  # e.g., "Answered", "Not Answered", "Marked For Review"
    option_ids: Dict[str, str] = field(default_factory=dict)  # {"A": "8232511201", ...}


@dataclass
class ParsedResponseSheet:
    candidate_name: str
    roll_number: str
    test_date: str
    test_time: str
    subject_title: str
    paper_code: str
    total_questions: int
    attempted_count: int
    skipped_count: int
    questions: List[ParsedQuestion]


# Paper code map from TCS iON subject strings
SUBJECT_TO_PAPER_MAP = {
    "COMPUTER SCIENCE": "CS",
    "INFORMATION TECHNOLOGY": "CS",
    "DATA SCIENCE": "DA",
    "ARTIFICIAL INTELLIGENCE": "DA",
    "MECHANICAL": "ME",
    "CIVIL": "CE",
    "ELECTRICAL": "EE",
    "ELECTRONICS": "EC",
    "COMMUNICATION": "EC",
    "INSTRUMENTATION": "IN",
    "CHEMICAL": "CH",
}

OPTION_INDEX_TO_LETTER = {
    "1": "A",
    "2": "B",
    "3": "C",
    "4": "D",
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
}


def extract_paper_code_from_subject(subject: str) -> str:
    """
    Extracts canonical 2-letter GATE paper code from subject description.
    """
    sub_upper = subject.upper()
    for key, code in SUBJECT_TO_PAPER_MAP.items():
        if key in sub_upper:
            return code
    # Default fallback
    words = re.findall(r"\b[A-Z]{2}\b", sub_upper)
    if words and words[0] in ["CS", "ME", "CE", "EE", "EC", "DA", "IN", "CH"]:
        return words[0]
    return "CS"


def parse_tcs_response_sheet(html_content: str) -> ParsedResponseSheet:
    """
    Parses a TCS iON Digialm HTML response sheet string into structured records.
    Handles varied HTML DOM structures across GATE years (tables, divs, spans).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Extract Candidate Header Details
    candidate_name = ""
    roll_number = ""
    test_date = ""
    test_time = ""
    subject_title = ""

    # Digialm candidate details table (usually top table or class main-info)
    header_tables = soup.find_all("table")
    for tbl in header_tables:
        text = tbl.get_text()
        if "Candidate Name" in text or "Roll No" in text or "Participant Name" in text:
            for row in tbl.find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                if len(cells) >= 2:
                    label = cells[0].lower()
                    val = cells[1]
                    if "candidate name" in label or "participant name" in label:
                        candidate_name = val
                    elif "roll no" in label or "participant id" in label or "candidate id" in label:
                        roll_number = val
                    elif "test date" in label or "exam date" in label:
                        test_date = val
                    elif "test time" in label:
                        test_time = val
                    elif "subject" in label:
                        subject_title = val

    # Fallback header regex if table parsing missed anything
    if not candidate_name:
        match = re.search(r"(?:Candidate|Participant)\s*Name\s*[:\-]?\s*([A-Za-z\s\.]+)", html_content)
        if match:
            candidate_name = match.group(1).split("\n")[0].strip()

    if not roll_number:
        match = re.search(r"(?:Roll\s*No|Participant\s*ID|Candidate\s*ID)\s*[:\-]?\s*([A-Za-z0-9]+)", html_content)
        if match:
            roll_number = match.group(1).strip()

    if not subject_title:
        match = re.search(r"Subject\s*[:\-]?\s*([A-Za-z\s&,]+)", html_content)
        if match:
            subject_title = match.group(1).split("\n")[0].strip()

    paper_code = extract_paper_code_from_subject(subject_title)

    # 2. Extract Questions
    questions: List[ParsedQuestion] = []

    # Find question blocks: Digialm wraps questions in div.question-pnl or table.menu-tbl
    menu_tables = soup.find_all("table", class_=lambda c: c and "menu-tbl" in c)
    if not menu_tables:
        # Fallback: Find tables containing "Question ID" or "Question Type"
        menu_tables = [t for t in soup.find_all("table") if "Question ID" in t.get_text()]

    q_idx = 1
    for tbl in menu_tables:
        props: Dict[str, str] = {}
        for row in tbl.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) >= 2:
                key = cells[0].rstrip(":").strip()
                val = cells[1].strip()
                props[key] = val

        q_id = props.get("Question ID", f"{paper_code}-Q{q_idx}")
        raw_type = props.get("Question Type", "MCQ").upper()
        raw_status = props.get("Status", "Not Answered")
        chosen_opt_raw = props.get("Chosen Option", "--").strip()
        given_ans_raw = props.get("Given Answer", "--").strip()

        # Determine Question Type
        q_type = "MCQ"
        if "MSQ" in raw_type:
            q_type = "MSQ"
        elif "NAT" in raw_type or "NUMERICAL" in raw_type:
            q_type = "NAT"
        elif given_ans_raw != "--":
            q_type = "NAT"

        # Determine Attempted vs Skipped Status
        status = "SKIPPED"
        chosen_options: Optional[List[str]] = None
        given_answer: Optional[str] = None

        # Check if answered
        is_answered = (
            "Answered" in raw_status
            and "Not Answered" not in raw_status
        ) or (
            chosen_opt_raw not in ["--", "None", "", "null"]
        ) or (
            given_ans_raw not in ["--", "None", "", "null"]
        )

        if is_answered:
            if q_type == "NAT":
                if given_ans_raw not in ["--", "None", "", "null"]:
                    status = "ATTEMPTED"
                    given_answer = given_ans_raw
            else:
                if chosen_opt_raw not in ["--", "None", "", "null"]:
                    status = "ATTEMPTED"
                    # Handle multiple options in MSQ e.g. "1, 3" or "1,2" or "A, C"
                    raw_parts = [p.strip() for p in chosen_opt_raw.replace(";", ",").split(",")]
                    opts = []
                    for p in raw_parts:
                        mapped = OPTION_INDEX_TO_LETTER.get(p.upper(), p.upper())
                        if mapped in ["A", "B", "C", "D"]:
                            opts.append(mapped)
                    if opts:
                        chosen_options = sorted(list(set(opts)))
                    else:
                        status = "SKIPPED"

        # Extract Option IDs if available
        opt_ids = {}
        for num, letter in [("1", "A"), ("2", "B"), ("3", "C"), ("4", "D")]:
            opt_key = f"Option {num} ID"
            if opt_key in props and props[opt_key] != "--":
                opt_ids[letter] = props[opt_key]

        questions.append(
            ParsedQuestion(
                question_number=q_idx,
                question_id=q_id,
                question_type=q_type,
                status=status,
                chosen_options=chosen_options,
                given_answer=given_answer,
                raw_status=raw_status,
                option_ids=opt_ids,
            )
        )
        q_idx += 1

    # If no menu tables found, use regex fallback to extract question blocks
    if not questions:
        pattern = re.compile(
            r"Question\s*ID\s*[:\-]?\s*([0-9]+).*?"
            r"(?:Question\s*Type\s*[:\-]?\s*([A-Za-z]+))?.*?"
            r"(?:Status\s*[:\-]?\s*([A-Za-z\s]+))?.*?"
            r"(?:Chosen\s*Option\s*[:\-]?\s*([0-9A-D,\s\-]+))?.*?"
            r"(?:Given\s*Answer\s*[:\-]?\s*([0-9\.\-\s]+))?",
            re.DOTALL | re.IGNORECASE,
        )
        for idx, match in enumerate(pattern.finditer(html_content), 1):
            q_id = match.group(1).strip()
            q_type_str = (match.group(2) or "MCQ").strip().upper()
            status_str = (match.group(3) or "Not Answered").strip()
            chosen_str = (match.group(4) or "--").strip()
            given_str = (match.group(5) or "--").strip()

            q_type = "MCQ"
            if "MSQ" in q_type_str:
                q_type = "MSQ"
            elif "NAT" in q_type_str or given_str != "--":
                q_type = "NAT"

            stat = "SKIPPED"
            opts = None
            ans = None

            if "Answered" in status_str and "Not Answered" not in status_str:
                if q_type == "NAT" and given_str != "--":
                    stat = "ATTEMPTED"
                    ans = given_str
                elif chosen_str != "--":
                    stat = "ATTEMPTED"
                    opts = [OPTION_INDEX_TO_LETTER.get(p.strip(), p.strip()) for p in chosen_str.split(",") if p.strip() in OPTION_INDEX_TO_LETTER]

            questions.append(
                ParsedQuestion(
                    question_number=idx,
                    question_id=q_id,
                    question_type=q_type,
                    status=stat,
                    chosen_options=opts,
                    given_answer=ans,
                    raw_status=status_str,
                )
            )

    attempted = sum(1 for q in questions if q.status == "ATTEMPTED")
    skipped = len(questions) - attempted

    return ParsedResponseSheet(
        candidate_name=candidate_name or "GATE Candidate",
        roll_number=roll_number or "GATE-UNSPECIFIED",
        test_date=test_date or "N/A",
        test_time=test_time or "N/A",
        subject_title=subject_title or paper_code,
        paper_code=paper_code,
        total_questions=len(questions),
        attempted_count=attempted,
        skipped_count=skipped,
        questions=questions,
    )


async def fetch_and_parse_response_sheet_url(url: str) -> ParsedResponseSheet:
    """
    Fetches candidate response sheet from live TCS iON Digialm URL
    and parses into structured records.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL: must begin with http:// or https://")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(clean_url, headers=headers)
            if resp.status_code != 200:
                raise ValueError(
                    f"Digialm server returned HTTP status {resp.status_code}. "
                    "Ensure the response sheet link is publicly accessible."
                )
            html_text = resp.text
    except httpx.RequestError as exc:
        raise ValueError(f"Failed to fetch Digialm response sheet: {str(exc)}")

    return parse_tcs_response_sheet(html_text)
