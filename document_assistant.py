"""Small, local assistant: document excerpts plus explicit price arithmetic."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

DOCS_DIR = Path(__file__).resolve().parent / "docs"
BROCHURE = "01_mgc_aurora_heights_brochure.md"
PRICES = "02_price_list_payment_plan.md"
POLICY = "03_booking_policy_faq.md"


def read_documents(directory=DOCS_DIR):
    documents = {}
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        date_match = re.search(r"(?:Issued|Effective|updated)\s+(?:\d+\s+)?([A-Z][a-z]+ \d{4})", text)
        parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
        documents[path.name] = {
            "title": text.splitlines()[0].lstrip("# "),
            "date": datetime.strptime(date_match[1], "%B %Y").date() if date_match else None,
            "sections": {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)},
        }
    return documents


def plain(text):
    return re.sub(r"\*\*|(?<!\w)\*(?!\w)", "", text).strip()


def result(text, references, documents, **extra):
    sources = []
    for filename, section in dict.fromkeys(references):
        doc = documents[filename]
        sources.append({"file": filename, "title": doc["title"], "section": section,
                        "date": doc["date"].strftime("%B %Y") if doc["date"] else "Undated"})
    return {"answer": text, "sources": sources, **extra}


def excerpts(references, documents, intro="Relevant passages from the supplied documents:"):
    text = "\n\n".join(f"{section}:\n{plain(documents[file]['sections'][section])}"
                        for file, section in references)
    return result(f"{intro}\n\n{text}", references, documents)


def transfer_answer(documents):
    references = [(POLICY, "Transfers"), (PRICES, "Other Charges")]
    fees = []
    for filename, section in references:
        passage = plain(documents[filename]["sections"][section])
        match = re.search(r"Transfer fee[^\d]*(\d+(?:\.\d+)?)%", passage, re.I)
        fees.append((Decimal(match[1]), documents[filename]["date"], filename))
    if fees[0][0] != fees[1][0] and (None in [x[1] for x in fees] or fees[0][1] == fees[1][1]):
        return excerpts(references, documents, "The supplied transfer fees conflict without a clear chronology. Ask management to resolve this.")
    newer, older = sorted(fees, key=lambda x: x[1] or datetime.min.date(), reverse=True)
    answer = (f"The current transfer fee in the supplied documents is {newer[0]}% of the current list price, "
              f"according to {documents[newer[2]]['title']} ({newer[1]:%B %Y}).")
    if newer[0] != older[0]:
        answer += (f" The older {older[1]:%B %Y} document states {older[0]}%. "
                   "The newer dated authoritative document has been used.")
    return result(answer, references, documents)


def price_answer(question, documents):
    block_match = re.search(r"block\s*([ab])\b", question)
    bed_match = re.search(r"\b([1-4])\s*[- ]?\s*(?:bed|bedroom)", question)
    references = [(PRICES, "Base Prices (Block A)"), (PRICES, "Base Prices (Block B)")]
    if not block_match or (not bed_match and "studio" not in question):
        return result("Please specify the block (A or B) and unit type so I can select the correct base price.", references, documents)
    block = block_match[1].upper()
    corner = "corner" in question
    unit = "Studio" if "studio" in question else {
        "1": "1-Bed Standard", "2": "2-Bed Corner" if corner else "2-Bed Standard",
        "3": "3-Bed Executive", "4": "4-Bed Penthouse",
    }[bed_match[1]]
    section = f"Base Prices (Block {block})"
    references = [(PRICES, section)]
    rows = [line.strip("| ").split("|") for line in documents[PRICES]["sections"][section].splitlines() if line.startswith("|")]
    row = next((r for r in rows if r[0].strip().lower() == unit.lower()), None)
    if row is None or (corner and unit != "2-Bed Corner"):
        return result("The supplied unit tables do not list that block/unit combination. I cannot quote a price for it.", references + [(BROCHURE, "Unit Configuration")], documents)
    base = Decimal(row[2].strip().replace(",", ""))
    floor_match = re.search(r"(?:floor\s*(\d+)|(\d+)(?:st|nd|rd|th)?\s+floor)", question)
    floor = int(floor_match[1] or floor_match[2]) if floor_match else None
    facing = "margalla" in question
    if facing and unit in ("Studio", "1-Bed Standard"):
        return excerpts([(BROCHURE, "Unit Configuration")], documents, "Studio and 1-Bed units are not available with a Margalla-facing orientation.")
    if floor is not None and (floor < 4 or floor > 22 or (unit == "4-Bed Penthouse" and floor < 20)):
        return excerpts([(BROCHURE, "Unit Configuration"), (BROCHURE, "Overview")], documents, "That residential floor/unit combination is not supported by the supplied documents.")
    # Above floor 12, Block B faces Margalla; preserve the explicit small-unit exception.
    inferred_facing = block == "B" and floor is not None and floor > 12 and unit not in ("Studio", "1-Bed Standard") and not facing
    facing = facing or inferred_facing
    base_only = "base" in question and not any(word in question for word in ["total", "premium", "including"])
    if base_only:
        answer = f"Block {block} {unit}: base price PKR {base:,.0f} ({row[1].strip()}). Location premiums and other charges are separate."
        if unit == "2-Bed Standard":
            answer += " This uses the Standard unit; the Corner unit has a separate base price."
        return result(answer, references, documents, base_price=float(base))
    premium_text = plain(documents[PRICES]["sections"]["Location Premiums"])
    premiums = []
    if floor is not None:
        for low, high, percent in re.findall(r"Floors (\d+)[–-](\d+):\s*\+(\d+)%", premium_text):
            if int(low) <= floor <= int(high):
                premiums.append((f"Floor {floor}", Decimal(percent)))
    for active, label in [(corner, "Corner unit"), (facing, "Margalla-facing")]:
        if active:
            percent = re.search(rf"{label}:\s*\+(\d+)%", premium_text)[1]
            premiums.append((label, Decimal(percent)))
    rate = sum((p for _, p in premiums), Decimal(0))
    total = base * (1 + rate / 100)
    lines = [f"Block {block} {unit} base: PKR {base:,.0f}."]
    lines.extend(f"{label}: +{percent}% = PKR {base * percent / 100:,.0f}." for label, percent in premiums)
    lines.append(f"Premiums are additive on the base: {rate}% total.\nPKR {base:,.0f} × (1 + {rate}/100) = PKR {total:,.0f}.")
    if inferred_facing:
        lines.append("Margalla-facing premium included because the brochure places this Block B unit above floor 12.")
        references.append((BROCHURE, "Unit Configuration"))
    if floor is None:
        lines.append("Floor was not specified: this is a subtotal before any applicable floor premium (and orientation premium if applicable).")
    lines.append("This is the unit price including the listed premiums, before discounts and other charges. Other charges are listed below separately:")
    lines.append(plain(documents[PRICES]["sections"]["Other Charges"]).split("- Transfer fee")[0].strip())
    references += [(PRICES, "Location Premiums"), (PRICES, "Other Charges")]
    return result("\n".join(lines), references, documents, base_price=float(base), premium_percent=float(rate), unit_price=float(total))


def answer_question(question, documents=None):
    documents = documents if documents is not None else read_documents()
    q = re.sub(r"\s+", " ", question.lower().replace("–", "-")).strip()
    checked = [(name, "All sections checked") for name in documents]
    if not q:
        return result("Please enter a question.", checked, documents)
    if re.search(r"\b(?:rent(?:al)?|yields?|return on investment|roi)\b", q):
        passage = documents[POLICY]["sections"]["Frequently Asked"]
        paragraph = re.search(r"\*\*What is the rental yield\?\*\*\s*(.*?)(?:\n\n|$)", passage, re.S)[1]
        return result(plain(paragraph), [(POLICY, "Frequently Asked")], documents)
    if "anchor" in q or "tenant" in q:
        return excerpts([(BROCHURE, "Commercial Podium")], documents)
    if "transfer" in q:
        fee = transfer_answer(documents)
        if any(term in q for term in ["overseas", "remote", "abroad", "person", "eligible", "when", "condition", "how"]):
            refs = [(POLICY, "Transfers"), (POLICY, "Overseas Buyers")]
            extra = excerpts(refs, documents)
            fee["answer"] += "\n\n" + extra["answer"]
            fee["sources"] += [s for s in extra["sources"] if s not in fee["sources"]]
        return fee
    if any(term in q for term in ["discount", "cash price", "upfront"]):
        return excerpts([(PRICES, "Discounts"), (PRICES, "Location Premiums"), (POLICY, "Overseas Buyers")], documents)
    if re.search(r"price|cost|total|premium|how much", q) and re.search(r"\bblock\b|\bbed|studio|penthouse", q):
        return price_answer(q, documents)
    topics = [
        (r"payment plan|instal|install|quarter", [(PRICES, "Standard Payment Plan (4 years)")]),
        (r"cancel|refund|default", [(POLICY, "Cancellations and Refunds")]),
        (r"possession|handover|complet|construction", [(BROCHURE, "Overview"), (POLICY, "Possession")]),
        (r"book|token|confirm", [(POLICY, "Booking Process"), (PRICES, "Standard Payment Plan (4 years)"), (PRICES, "Notes")]),
        (r"overseas|roshan|remot", [(POLICY, "Overseas Buyers")]),
        (r"gas|loan|bank|mark.?up|change.*unit", [(POLICY, "Frequently Asked")]),
        (r"amenit|pool|parking|gym|security|power|internet|fire", [(BROCHURE, "Amenities"), (PRICES, "Other Charges")]),
        (r"approval|noc|cda|environment", [(BROCHURE, "Approvals")]),
        (r"office|contact|phone|opening|hours", [(BROCHURE, "Sales Office")]),
        (r"area|size|square|sq ft|configuration|available|orientation", [(BROCHURE, "Unit Configuration")]),
        (r"location|where|tower|storey|project", [(BROCHURE, "Overview")]),
    ]
    references = []
    for pattern, refs in topics:
        if re.search(pattern, q):
            references.extend(refs)
    if references:
        references = list(dict.fromkeys(references))
        # Never reproduce the obsolete fee without its resolution, even in parking/charges excerpts.
        response = excerpts(references, documents, "These supplied passages may help; they may not answer every part of your question. No additional facts are inferred.")
        if (PRICES, "Other Charges") in references:
            fee = transfer_answer(documents)
            response["answer"] = fee["answer"] + "\n\n" + response["answer"]
            response["sources"] += [s for s in fee["sources"] if s not in response["sources"]]
        return response
    return result("The supplied documents do not provide that information. Please ask the marketing manager.", checked, documents)
