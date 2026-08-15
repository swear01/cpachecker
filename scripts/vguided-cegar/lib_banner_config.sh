# Shared helpers for banner-derived config extraction (kept in sync with
# rebuild_summary_csv.py::_config_from_log). Sources: run_benchmark_set.sh,
# rebuild_summary_csv.sh.
#
# The CPAchecker startup banner is "CPAchecker <version> / <analysis-name> ...";
# the analysis name (e.g. svcomp26-vguide) is the canonical config label.
banner_config() {
  local log="$1"
  grep -m1 -oE 'CPAchecker [^ ]+ / [^ ]+' "$log" 2>/dev/null | awk '{print $NF}' || true
}

# Quote a value for the hand-built CSV (commas/quotes/newlines).
csv_field() {
  local v="$1"
  if [[ "$v" == *","* || "$v" == *"\""* || "$v" == *$'\n'* ]]; then
    printf '"%s"' "${v//\"/\"\"}"
  else
    printf '%s' "$v"
  fi
}
