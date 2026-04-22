# Quickstart

```bash
git clone https://github.com/Velascat/SwitchBoard
cd SwitchBoard
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
bash scripts/run_dev.sh
bash scripts/smoke_test.sh
```

Verify the selector runtime:

```bash
curl http://localhost:20401/health
curl -X POST http://localhost:20401/route \
  -H "Content-Type: application/json" \
  -d '{"task_id":"demo-1","project_id":"demo","task_type":"documentation","execution_mode":"goal","goal_text":"Refresh docs","target":{"repo_key":"docs","clone_url":"https://example.invalid/docs.git","base_branch":"main","allowed_paths":[]},"priority":"normal","risk_level":"low","constraints":{"allowed_paths":[],"require_clean_validation":true},"validation_profile":{"profile_name":"default","commands":[]},"branch_policy":{"push_on_success":true,"open_pr":false},"labels":[]}'
```
