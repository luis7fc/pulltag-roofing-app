
import pdfplumber
import re
import pandas as pd

def parse_pdf_budget_all_lots(pdf_path: str) -> pd.DataFrame:
    records = []
    job_number = None
    community = None
    current_lot = None
    last_known_lot = None

    lot_header_pattern = re.compile(r"^(\d{4})\s+[\d\s\w]+?\(\w+\)")
    flex_item_pattern = re.compile(
        r"^\s*([A-Za-z0-9\(\)\+\"'#\/\-]{2,})\s+(.+?)\s+([\d.]+)\s+(EA|SQ|BNDL|ROLL|PC|BUND|BOX)\s*$"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().splitlines()
            if not lines:
                print(f"[DEBUG] No text found on page {page.page_number}")

            for idx, line in enumerate(lines):
                if re.match(r"^\d{5}-\d{3}\s", line.strip()):
                    job_number = re.match(r"^(\d{5}-\d{3})", line.strip()).group(1)
                    community = line.strip().split(job_number)[-1].strip()

                lot_match = lot_header_pattern.match(line)
                if lot_match:
                    current_lot = lot_match.group(1)
                    last_known_lot = current_lot

                if line.strip().startswith("L"):
                    continue

                match = flex_item_pattern.match(line)
                if match and last_known_lot:
                    code, desc, qty, uom = match.groups()
                    records.append({
                        "Community": community,
                        "Job Number": job_number,
                        "Lot Number": last_known_lot,
                        "Cost Code": code.strip().upper(),
                        "Description": desc.strip(),
                        "Units Budget": float(qty),
                        "UOM": uom
                    })
                    
                    print(f"[DEBUG] Parsed: job={job_number}, lot={last_known_lot}, code={code}, desc={desc}, qty={qty}, uom={uom}")


    return pd.DataFrame(records)
