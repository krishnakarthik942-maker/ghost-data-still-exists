import argparse
import csv
import json
import os
import sys

from audit_agent import AuditAgent

def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists - Deletion Audit Pipeline")
    parser.add_argument("--input", default="dataset/deletion_requests.csv", help="Input deletion requests CSV path")
    parser.add_argument("--output", default="output.csv", help="Output predictions CSV path")
    parser.add_argument("--dataset-dir", default="dataset", help="Dataset directory path")
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output
    dataset_dir = args.dataset_dir

    if not os.path.exists(input_path):
        print(f"Error: input file {input_path} not found.")
        sys.exit(1)

    print(f"Initializing AuditAgent with dataset_dir='{dataset_dir}'...")
    agent = AuditAgent(dataset_dir=dataset_dir)

    print(f"Reading requests from {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))

    print(f"Processing {len(reader)} deletion requests with batch-level correlation...")
    results = []
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    batch_outputs = agent.audit_batch(reader)
    for cid, status, steps_json in batch_outputs:
        status_counts[status] = status_counts.get(status, 0) + 1
        results.append({
            'case_id': cid,
            'deletion_status': status,
            'steps_json': steps_json
        })

    # Sort results by case_id ascending (handling numerical sorting if applicable)
    def case_sort_key(item):
        cid = item['case_id']
        parts = cid.split('_')
        if len(parts) == 2 and parts[1].isdigit():
            return (parts[0], int(parts[1]))
        return (cid, 0)

    results.sort(key=case_sort_key)

    print(f"Writing {len(results)} rows to {output_path}...")
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['case_id', 'deletion_status', 'steps_json'])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"\nSuccessfully generated {output_path} with {len(results)} rows.")
    print(f"Summary of predictions:")
    for st, cnt in sorted(status_counts.items()):
        print(f"  {st:15}: {cnt:4d} ({cnt / len(results) * 100:.1f}%)")

if __name__ == '__main__':
    main()
