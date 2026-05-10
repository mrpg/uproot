# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

import json
import subprocess

commits = (
    subprocess.check_output(
        ["git", "log", "--format=%H %aI", "--reverse"],
        text=True,
    )
    .strip()
    .splitlines()
)

print("date", "commit", "code", sep=",")

for line in commits:
    sha, date = line.split(" ", 1)
    date_short = date[:10]
    subprocess.run(["git", "checkout", sha, "--quiet"], check=True)
    result = subprocess.run(
        ["tokei", "--streaming", "json", "-t", "Python", "src/uproot"],
        capture_output=True,
        text=True,
    )
    code = 0

    for jsonline in result.stdout.strip().splitlines():
        entry = json.loads(jsonline)
        code += entry["stats"]["stats"]["code"]

    print(date_short, sha, code, sep=",")

subprocess.run(["git", "checkout", "-", "--quiet"], check=True)
