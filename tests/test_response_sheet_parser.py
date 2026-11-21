import pytest
from backend.app.services.response_sheet_parser import (
    extract_paper_code_from_subject,
    parse_tcs_response_sheet,
)

SAMPLE_TCS_ION_HTML = """
<!DOCTYPE html>
<html>
<head><title>GATE 2025 Response Sheet</title></head>
<body>
  <table>
    <tr><td>Participant ID</td><td>CS25S38099881</td></tr>
    <tr><td>Participant Name</td><td>Aakash Gupta</td></tr>
    <tr><td>Test Center Name</td><td>iON Digital Zone iDZ New Delhi</td></tr>
    <tr><td>Test Date</td><td>08/02/2025</td></tr>
    <tr><td>Test Time</td><td>09:30 AM - 12:30 PM</td></tr>
    <tr><td>Subject</td><td>CS Computer Science and Information Technology</td></tr>
  </table>

  <!-- Question 1: MCQ Single Choice Attempted -->
  <div class="question-pnl">
    <table class="menu-tbl">
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Question ID :</td><td>823251501</td></tr>
      <tr><td>Option 1 ID :</td><td>8232511201</td></tr>
      <tr><td>Option 2 ID :</td><td>8232511202</td></tr>
      <tr><td>Option 3 ID :</td><td>8232511203</td></tr>
      <tr><td>Option 4 ID :</td><td>8232511204</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>2</td></tr>
    </table>
  </div>

  <!-- Question 2: MSQ Multiple Choice Attempted -->
  <div class="question-pnl">
    <table class="menu-tbl">
      <tr><td>Question Type :</td><td>MSQ</td></tr>
      <tr><td>Question ID :</td><td>823251502</td></tr>
      <tr><td>Option 1 ID :</td><td>8232511205</td></tr>
      <tr><td>Option 2 ID :</td><td>8232511206</td></tr>
      <tr><td>Option 3 ID :</td><td>8232511207</td></tr>
      <tr><td>Option 4 ID :</td><td>8232511208</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>1, 3</td></tr>
    </table>
  </div>

  <!-- Question 3: NAT Numerical Value Attempted -->
  <div class="question-pnl">
    <table class="menu-tbl">
      <tr><td>Question Type :</td><td>NAT</td></tr>
      <tr><td>Question ID :</td><td>823251503</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Given Answer :</td><td>24.5</td></tr>
    </table>
  </div>

  <!-- Question 4: Skipped Question -->
  <div class="question-pnl">
    <table class="menu-tbl">
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Question ID :</td><td>823251504</td></tr>
      <tr><td>Status :</td><td>Not Answered</td></tr>
      <tr><td>Chosen Option :</td><td>--</td></tr>
    </table>
  </div>
</body>
</html>
"""


def test_subject_to_paper_code_extraction():
    assert extract_paper_code_from_subject("CS Computer Science and Information Technology") == "CS"
    assert extract_paper_code_from_subject("Data Science and Artificial Intelligence") == "DA"
    assert extract_paper_code_from_subject("Mechanical Engineering") == "ME"
    assert extract_paper_code_from_subject("Civil Engineering") == "CE"
    assert extract_paper_code_from_subject("Electrical Engineering") == "EE"
    assert extract_paper_code_from_subject("Electronics and Communication Engineering") == "EC"


def test_tcs_response_sheet_header_parsing():
    parsed = parse_tcs_response_sheet(SAMPLE_TCS_ION_HTML)
    assert parsed.candidate_name == "Aakash Gupta"
    assert parsed.roll_number == "CS25S38099881"
    assert parsed.paper_code == "CS"
    assert parsed.test_date == "08/02/2025"
    assert parsed.total_questions == 4
    assert parsed.attempted_count == 3
    assert parsed.skipped_count == 1


def test_tcs_response_sheet_questions_parsing():
    parsed = parse_tcs_response_sheet(SAMPLE_TCS_ION_HTML)
    q1 = parsed.questions[0]
    assert q1.question_id == "823251501"
    assert q1.question_type == "MCQ"
    assert q1.status == "ATTEMPTED"
    assert q1.chosen_options == ["B"]  # Option 2 mapped to B

    q2 = parsed.questions[1]
    assert q2.question_id == "823251502"
    assert q2.question_type == "MSQ"
    assert q2.status == "ATTEMPTED"
    assert q2.chosen_options == ["A", "C"]  # Options 1, 3 mapped to A, C

    q3 = parsed.questions[2]
    assert q3.question_id == "823251503"
    assert q3.question_type == "NAT"
    assert q3.status == "ATTEMPTED"
    assert q3.given_answer == "24.5"

    q4 = parsed.questions[3]
    assert q4.question_id == "823251504"
    assert q4.status == "SKIPPED"
    assert q4.chosen_options is None
