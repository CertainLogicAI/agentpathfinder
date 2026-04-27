# Build Spec: Add CSV Export to Pro Dashboard

## Goal
Add CSV export functionality to the Pro Dashboard with one-click download.

## Requirements
1. Export button on dashboard
2. CSV format with headers: task_id, name, state, steps, completed, failed, created_at
3. Works with filtered agent views
4. File download (not just API endpoint)

## Steps
1. Add `/export` route to `pro_dashboard.py`
2. Generate CSV via `io.StringIO` + `csv.writer`
3. Return as `Response` with proper headers
4. Add export buttons to HTML template
5. Test with sample data

## Testing
- Create 3+ tasks
- Click CSV export
- Verify file contents
- Check with AgentPathfinder audit
