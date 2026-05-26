# Batch Evaluation Notes

## Pipeline

```
discover_candidates.sh → batch_eval.sh stock → batch_eval.sh vmodes
     ↓                        ↓                        ↓
 263 programs           stock_scan.csv            summary.csv
```

## Known Issues & Workarounds

### 1. Background stdout buffering

**Symptom:** `nohup bash batch.sh > run.log 2>&1 &` produces no output for hours.

**Root cause:** When bash stdout is a file (not TTY), `echo` uses block buffering (4KB). Output appears only when buffer fills or process exits.

**Failed attempts:**
- `nohup env PATH=... bash batch.sh` — buffered
- `stdbuf -oL nohup env ... bash batch.sh` — `stdbuf` only affects C stdio, not bash builtins
- `nohup stdbuf -oL bash -c '...'` — `stdbuf` lost in subshell

**Solution:** Use `tmux` / `screen` which provides a pseudo-TTY:
```bash
tmux new-session -d -s vg_batch bash /path/to/script.sh
tmux capture-pane -t vg_batch -p | tail -20
```

**Alternative:** Run foreground in a regular terminal. TTY → line-buffered.

### 2. `set -e` kills batch on first non-zero exit

**Fix:** Removed `set -euo pipefail`. Use `|| true` on commands that may fail:
```bash
run_cpa() {
  timeout "$LLM_TIMEOUT" ... > "$outlog" 2>&1 < /dev/null || true
}
```

### 3. stdin consumption by child processes

**Symptom:** `while read` loop stops after 2-3 iterations.

**Root cause:** CPAchecker or `timeout` reads from inherited stdin, consuming remaining lines.

**Fix:** `< /dev/null` on child process stdin:
```bash
timeout ... > "$log" 2>&1 < /dev/null
```

### 4. Array benchmarks too slow / unsupported

**Symptom:** `array_*.c` benchmarks run forever (300s each, UNKNOWN result).

**Fix:** Filter candidates:
```bash
grep -v -E "array_|array3|_abstracted|multivar|simple_[0-9]"
```

### 5. Candidates file must persist

**Symptom:** tmux session dies immediately with "No such file".

**Fix:** Generate candidates file BEFORE launching tmux:
```bash
scripts/vguided-cegar/discover_candidates.sh | grep -v ... > /tmp/vg_candidates.txt
# then launch tmux referencing /tmp/vg_candidates.txt
```

## Running the Batch

```bash
cd /home/swear01/cpachecker

# 1. Generate candidates
scripts/vguided-cegar/discover_candidates.sh | \
  grep -v -E "array_|array3|_abstracted|multivar|simple_[0-9]" \
  > /tmp/vg_candidates.txt

# 2. Launch in tmux
mkdir -p results/vguided-cegar/batch_DATE
tmux new-session -d -s vg_batch bash -c "
  export PATH=/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin:\$PATH
  export JAVA=/home/swear01/FMPA2/external/jdk-21/jdk-21.0.10+7/bin/java
  export DEEPSEEK_API_KEY=your_key
  export HEAP=8000M TIMELIMIT=300 LLM_TIMEOUT=360
  bash scripts/vguided-cegar/batch_eval.sh all \
    /tmp/vg_candidates.txt \
    results/vguided-cegar/batch_DATE
"

# 3. Monitor
tmux capture-pane -t vg_batch -p | tail -20
tmux attach -t vg_batch  # Ctrl+B D to detach
cat results/vguided-cegar/batch_DATE/summary.csv
```
