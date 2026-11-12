#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tag main as vX.Y.Z, push it (the mirror carries it to GitHub, whose workflow publishes there), then publish
# the Gitea release with the same archive layout. Rerun after a failure: an existing tag is reused.
#   tools/release.sh 0.2.0
#   GITEA_TOKEN_FILE=~/.tokens/gitea_pat tools/release.sh 0.2.0
set -euo pipefail

api=https://homegit.gyozamancave.fr/api/v1/repos/billisdead/noctalia-themes
v=${1:?usage: tools/release.sh X.Y.Z}
[[ $v =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo "not a SemVer X.Y.Z: $v" >&2; exit 1; }
tag=v$v name=noctalia-themes-$v

tok=${GITEA_TOKEN_FILE:-}
for f in ~/.tokens/gitea_pat ~/gitea-trucs/postiz-helm/.token; do [[ -z $tok && -r $f ]] && tok=$f; done
[[ -r $tok ]] || { echo "no Gitea token: set GITEA_TOKEN_FILE" >&2; exit 1; }
# Token goes through stdin, never argv.
gitea() { printf 'Authorization: Bearer %s\n' "$(tr -d '\n' < "$tok")" | curl -sf -H @- "$@"; }

cd "$(git rev-parse --show-toplevel)"
[[ $(git branch --show-current) == main ]] || { echo "switch to main first" >&2; exit 1; }
git diff --quiet HEAD || { echo "working tree not clean" >&2; exit 1; }
git pull -q --ff-only

# Same checks as .github/workflows/release.yml, so a mismatch stops here before anything is pushed.
grep -q "^VERSION = \"$v\"$" app/main.py || { echo "app/main.py VERSION is not $v" >&2; exit 1; }
grep -q "<release version=\"$v\"" data/com.billisdead.NoctaliaThemes.metainfo.xml || { echo "metainfo has no release $v" >&2; exit 1; }
grep -q "^## \[$v\]" CHANGELOG.md || { echo "CHANGELOG.md has no section $v" >&2; exit 1; }

if gitea "$api/releases/tags/$tag" >/dev/null; then echo "Gitea release $tag already exists" >&2; exit 1; fi
git rev-parse -q --verify "refs/tags/$tag" >/dev/null || git tag -a "$tag" -m "Noctalia Themes $v"
git push -q origin "$tag"

out=$(mktemp -d); trap 'rm -rf "$out"' EXIT
git archive --prefix="$name/" -o "$out/$name.tar.gz" "$tag"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")
notes=$(git show "$tag:CHANGELOG.md" | awk -v v="$v" '$0 ~ "^## \\[" v "\\]" {f=1; next} /^## \[/ {f=0} f')

python3 -c 'import json,sys; print(json.dumps({"tag_name": sys.argv[1], "name": "Noctalia Themes " + sys.argv[2], "body": sys.argv[3]}))' \
  "$tag" "$v" "$notes" > "$out/release.json"
id=$(gitea -X POST -H 'Content-Type: application/json' --data-binary @"$out/release.json" "$api/releases" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
for f in "$name.tar.gz" "$name.tar.gz.sha256"; do
  gitea -X POST -F "attachment=@$out/$f" "$api/releases/$id/assets?name=$f" >/dev/null
done
echo "Gitea release $tag published; GitHub's follows from the mirror (Actions tab)."
