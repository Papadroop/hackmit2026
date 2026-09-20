#!/usr/bin/env bash
# Regenerate contract/types.ts from contract/schema.json.
# json-schema-to-typescript only emits definitions reachable from the root, so a wrapper that
# references both Event and Analysis is generated first; v15 crashes on this schema, v13 works.
set -euo pipefail
cd "$(dirname "$0")/../.."
WRAPPER="$(mktemp -t contract-wrapper.XXXXXX).json"
node -e '
const fs = require("fs");
const s = JSON.parse(fs.readFileSync("contract/schema.json", "utf8"));
const w = { "$schema": s["$schema"], title: "Contract", type: "object",
  properties: { event: { "$ref": "#/definitions/Event" }, analysis: { "$ref": "#/definitions/Analysis" } },
  additionalProperties: false, definitions: s.definitions };
fs.writeFileSync(process.argv[1], JSON.stringify(w));
' "$WRAPPER"
cd frontend
npx --yes -p json-schema-to-typescript@13 json2ts -i "$WRAPPER" -o ../contract/types.ts --no-additionalProperties \
  --bannerComment "/* Generated from contract/schema.json by contract/tools/gen_types.sh. Do not edit. */"
rm -f "$WRAPPER"
echo "wrote contract/types.ts"
