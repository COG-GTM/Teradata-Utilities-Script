#!/usr/bin/env python3
"""
Generate sample bank customer data and verify Teradata MultiLoad upsert logic.

This script:
1. Generates customer_existing.csv (500 rows) - the "before" state
2. Generates customer_incoming.csv (150 rows) - the upsert input (CSV)
3. Generates customer_incoming_pipe.txt (150 rows) - pipe-delimited input for Teradata
4. Computes target_output.csv (550 rows) - the expected "after" state
5. Runs verification checks to ensure correctness

The Teradata MultiLoad script (CustomerUPDATE.ml) performs:
  UPDATE: SET YEARS_WITH_BANK, INCOME, AGE WHERE CUST_ID matches
  INSERT: all 7 columns for new CUST_ID values

Key verification: updated rows keep ORIGINAL nbr_children, gender, marital_status.
"""

import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

COLUMNS = ["cust_id", "income", "age", "years_with_bank", "nbr_children", "gender", "marital_status"]

# --- Deterministic data generation formulas ---

def generate_row(n):
    """Generate a single row of customer data based on row number n (1-based)."""
    cust_id = f"C{n:04d}"
    income = 20000 + ((n * 271) % 130001)
    age = 18 + (n * 37) % 53
    years_with_bank = 1 + (n * 13) % 30
    nbr_children = (n * 7) % 6
    gender = "M" if n % 2 == 1 else "F"
    marital_status = "Y" if n % 3 != 0 else "N"
    return {
        "cust_id": cust_id,
        "income": income,
        "age": age,
        "years_with_bank": years_with_bank,
        "nbr_children": nbr_children,
        "gender": gender,
        "marital_status": marital_status,
    }


def generate_existing_data():
    """Generate 500 rows of existing customer data (C0001 to C0500)."""
    return [generate_row(n) for n in range(1, 501)]


def generate_incoming_data(existing_data):
    """
    Generate 150 rows of incoming upsert data:
    - 100 UPDATE rows: C0005, C0010, C0015, ..., C0500 (every 5th starting from 5)
    - 50 INSERT rows: C0501 to C0550
    """
    existing_by_id = {row["cust_id"]: row for row in existing_data}
    incoming = []

    # 100 UPDATE rows: every 5th customer starting from C0005
    update_ids = [f"C{n:04d}" for n in range(5, 501, 5)]
    assert len(update_ids) == 100, f"Expected 100 update IDs, got {len(update_ids)}"

    for cust_id in update_ids:
        existing = existing_by_id[cust_id]
        incoming.append({
            "cust_id": cust_id,
            "income": existing["income"] + 5000,
            "age": existing["age"] + 1,
            "years_with_bank": existing["years_with_bank"] + 2,
            "nbr_children": 9,        # deliberately different
            "gender": "X",            # deliberately different
            "marital_status": "Z",    # deliberately different
        })

    # 50 INSERT rows: C0501 to C0550, using same formula
    for n in range(501, 551):
        incoming.append(generate_row(n))

    return incoming


def compute_target_output(existing_data, incoming_data):
    """
    Apply the Teradata MultiLoad upsert logic:
    - UPDATE existing rows: only income, age, years_with_bank from incoming
    - INSERT new rows: all columns from incoming
    """
    existing_by_id = {row["cust_id"]: dict(row) for row in existing_data}
    incoming_by_id = {row["cust_id"]: row for row in incoming_data}

    target = {}

    # Start with all existing rows
    for cust_id, row in existing_by_id.items():
        target[cust_id] = dict(row)

    # Apply upsert logic
    for cust_id, inc_row in incoming_by_id.items():
        if cust_id in target:
            # UPDATE: only set income, age, years_with_bank
            target[cust_id]["income"] = inc_row["income"]
            target[cust_id]["age"] = inc_row["age"]
            target[cust_id]["years_with_bank"] = inc_row["years_with_bank"]
            # nbr_children, gender, marital_status remain unchanged
        else:
            # INSERT: all columns
            target[cust_id] = dict(inc_row)

    # Sort by cust_id
    sorted_rows = [target[k] for k in sorted(target.keys())]
    return sorted_rows


def write_csv(filepath, rows):
    """Write rows to a CSV file with header."""
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written: {filepath} ({len(rows)} rows)")


def write_pipe_delimited(filepath, rows):
    """Write rows to a pipe-delimited file without header."""
    with open(filepath, "w", newline="") as f:
        for row in rows:
            line = "|".join(str(row[col]) for col in COLUMNS)
            f.write(line + "\n")
    print(f"  Written: {filepath} ({len(rows)} rows)")


def verify(existing_data, incoming_data, target_data):
    """Run all verification checks. Returns True if all pass."""
    existing_by_id = {row["cust_id"]: row for row in existing_data}
    incoming_by_id = {row["cust_id"]: row for row in incoming_data}
    target_by_id = {row["cust_id"]: row for row in target_data}

    update_ids = set(cid for cid in incoming_by_id if cid in existing_by_id)
    insert_ids = set(cid for cid in incoming_by_id if cid not in existing_by_id)
    unchanged_ids = set(existing_by_id.keys()) - update_ids

    errors = []
    checks_passed = 0
    total_checks = 0

    def check(condition, message):
        nonlocal checks_passed, total_checks
        total_checks += 1
        if condition:
            checks_passed += 1
        else:
            errors.append(message)

    # Check 1: Total row count
    check(len(target_data) == 550, f"Total rows: expected 550, got {len(target_data)}")

    # Check 2: No duplicate cust_id
    target_ids = [row["cust_id"] for row in target_data]
    check(len(target_ids) == len(set(target_ids)),
          f"Duplicate cust_ids found: {len(target_ids)} total vs {len(set(target_ids))} unique")

    # Check 3: 400 unchanged rows
    unchanged_count = 0
    for cust_id in unchanged_ids:
        if cust_id in target_by_id:
            if target_by_id[cust_id] == existing_by_id[cust_id]:
                unchanged_count += 1
            else:
                errors.append(f"Row {cust_id} should be unchanged but differs")
    check(unchanged_count == 400,
          f"Unchanged rows: expected 400, got {unchanged_count}")

    # Check 4: 100 updated rows have correct values
    update_correct = 0
    for cust_id in update_ids:
        t = target_by_id.get(cust_id)
        e = existing_by_id[cust_id]
        i = incoming_by_id[cust_id]
        if t is None:
            errors.append(f"Updated row {cust_id} missing from target")
            continue

        row_ok = True
        # Updated columns should come from incoming
        if t["income"] != i["income"]:
            errors.append(f"{cust_id}: income expected {i['income']}, got {t['income']}")
            row_ok = False
        if t["age"] != i["age"]:
            errors.append(f"{cust_id}: age expected {i['age']}, got {t['age']}")
            row_ok = False
        if t["years_with_bank"] != i["years_with_bank"]:
            errors.append(f"{cust_id}: years_with_bank expected {i['years_with_bank']}, got {t['years_with_bank']}")
            row_ok = False
        # Non-updated columns should come from existing
        if t["nbr_children"] != e["nbr_children"]:
            errors.append(f"{cust_id}: nbr_children expected {e['nbr_children']} (existing), got {t['nbr_children']}")
            row_ok = False
        if t["gender"] != e["gender"]:
            errors.append(f"{cust_id}: gender expected {e['gender']} (existing), got {t['gender']}")
            row_ok = False
        if t["marital_status"] != e["marital_status"]:
            errors.append(f"{cust_id}: marital_status expected {e['marital_status']} (existing), got {t['marital_status']}")
            row_ok = False

        if row_ok:
            update_correct += 1

    check(update_correct == 100,
          f"Correctly updated rows: expected 100, got {update_correct}")

    # Check 5: 50 new rows match incoming exactly
    insert_correct = 0
    for cust_id in insert_ids:
        t = target_by_id.get(cust_id)
        i = incoming_by_id[cust_id]
        if t is None:
            errors.append(f"Inserted row {cust_id} missing from target")
            continue
        if t == i:
            insert_correct += 1
        else:
            errors.append(f"Inserted row {cust_id} doesn't match incoming: target={t}, incoming={i}")

    check(insert_correct == 50,
          f"Correctly inserted rows: expected 50, got {insert_correct}")

    # Check 6: Specific example - C0005
    print("\n--- Spot Check: C0005 ---")
    e5 = existing_by_id.get("C0005")
    i5 = incoming_by_id.get("C0005")
    t5 = target_by_id.get("C0005")
    if e5 and i5 and t5:
        print(f"  Existing:  income={e5['income']}, age={e5['age']}, ywb={e5['years_with_bank']}, "
              f"children={e5['nbr_children']}, gender={e5['gender']}, marital={e5['marital_status']}")
        print(f"  Incoming:  income={i5['income']}, age={i5['age']}, ywb={i5['years_with_bank']}, "
              f"children={i5['nbr_children']}, gender={i5['gender']}, marital={i5['marital_status']}")
        print(f"  Target:    income={t5['income']}, age={t5['age']}, ywb={t5['years_with_bank']}, "
              f"children={t5['nbr_children']}, gender={t5['gender']}, marital={t5['marital_status']}")
        check(t5["income"] == i5["income"] and t5["age"] == i5["age"] and t5["years_with_bank"] == i5["years_with_bank"],
              "C0005: updated columns should come from incoming")
        check(t5["nbr_children"] == e5["nbr_children"] and t5["gender"] == e5["gender"] and t5["marital_status"] == e5["marital_status"],
              "C0005: non-updated columns should come from existing (NOT incoming 9/X/Z)")
    else:
        errors.append("C0005 spot check: missing data in one of the datasets")

    # Check 7: Sorted order
    check(target_ids == sorted(target_ids), "Target output is not sorted by cust_id")

    return checks_passed, total_checks, errors


def main():
    print("=" * 60)
    print("Teradata MultiLoad Upsert - Data Generator & Verifier")
    print("=" * 60)

    # Step 1: Generate existing data
    print("\n[1] Generating customer_existing.csv (500 rows)...")
    existing_data = generate_existing_data()
    write_csv(os.path.join(SCRIPT_DIR, "customer_existing.csv"), existing_data)

    # Step 2: Generate incoming data
    print("\n[2] Generating incoming data (150 rows)...")
    incoming_data = generate_incoming_data(existing_data)
    write_csv(os.path.join(SCRIPT_DIR, "customer_incoming.csv"), incoming_data)
    write_pipe_delimited(os.path.join(SCRIPT_DIR, "customer_incoming_pipe.txt"), incoming_data)

    # Step 3: Compute target output
    print("\n[3] Computing target_output.csv (expected 550 rows)...")
    target_data = compute_target_output(existing_data, incoming_data)
    write_csv(os.path.join(SCRIPT_DIR, "target_output.csv"), target_data)

    # Step 4: Verify
    print("\n[4] Running verification checks...")
    passed, total, errors = verify(existing_data, incoming_data, target_data)

    print(f"\n{'=' * 60}")
    print(f"VERIFICATION SUMMARY: {passed}/{total} checks passed")
    print(f"{'=' * 60}")

    if errors:
        print("\nFAILURES:")
        for err in errors:
            print(f"  - {err}")
        print(f"\nResult: FAILED")
        sys.exit(1)
    else:
        print(f"\nResult: ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
