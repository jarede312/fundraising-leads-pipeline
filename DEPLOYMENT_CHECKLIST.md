# Deployment Checklist - Render.com

Use this checklist to track your deployment progress.

## Pre-Deployment

- [ ] GitHub account created (https://github.com)
- [ ] GitHub repository created (or use `gh repo create`)
- [ ] Code pushed to GitHub main branch
- [ ] Render account created (https://render.com/auth/signup)

## Step 1: Create PostgreSQL Database

- [ ] Logged into Render Dashboard
- [ ] Clicked **New +** → **PostgreSQL**
- [ ] Named the database `fundraising-db`
- [ ] Created the database
- [ ] Database is running (status shows green "Available")
- [ ] Copied the **Internal Database URL** to clipboard
  - Format: `postgres://username:password@internal-hostname:5432/database`
  - ⚠️ Use **Internal URL**, NOT external URL

## Step 2: Prepare Environment Variables

- [ ] Have your PostgreSQL **Internal Database URL** ready
- [ ] Have your Anthropic API key ready (https://console.anthropic.com/keys)
- [ ] Know your desired Render region (usually US East or closest to you)

## Step 3: Deploy Web Service

- [ ] Clicked **New +** → **Web Service** in Render Dashboard
- [ ] Selected GitHub repository `fundraising-leads-pipeline`
- [ ] Connected GitHub account (if first time)
- [ ] Filled in service details:
  - [ ] **Name**: `fundraising-webapp`
  - [ ] **Environment**: Python 3
  - [ ] **Build Command**: `pip install -r requirements.txt`
  - [ ] **Start Command**: `uvicorn webapp.main:app --host 0.0.0.0 --port $PORT`
  - [ ] **Region**: Same as database (important!)
  - [ ] **Plan**: Standard ($7) or Free (limited)
- [ ] Added **Environment Variables**:
  - [ ] `PG_DSN` = [paste Internal Database URL]
  - [ ] `ANTHROPIC_API_KEY` = [paste your API key]
  - [ ] `LLM_MODEL` = `claude-opus-5`
  - [ ] `USER_AGENT` = `FundraisingProspectEngine/0.1`
  - [ ] `PYTHONUNBUFFERED` = `1`
- [ ] Clicked **Create Web Service**
- [ ] Waited for deployment (3-5 minutes)
- [ ] Deployment shows "Available" (green status)

## Step 4: Load Data

- [ ] Tested the app at `https://fundraising-webapp.onrender.com`
  - Shows home page (may be empty)
- [ ] Ran ingest pipeline against Render database:
  ```bash
  export PG_DSN="your-render-internal-database-url"
  python -m ingest.phase1_nces
  python -m ingest.phase2_dpi
  # ... etc for remaining phases
  ```
- [ ] Data appears in the web app after refresh

## Step 5: Verify Production

- [ ] School list displays data
- [ ] Filters work (sort, pagination)
- [ ] School detail page loads
- [ ] Activity logging works (or tested locally)
- [ ] Queue mode works
- [ ] Home page shows today's priority list

## Optional: Additional Configuration

- [ ] Enabled auto-deploy from GitHub (automatic on new push)
- [ ] Set up database backups in Render
- [ ] Set up monitoring/alerts (Render dashboard)
- [ ] Shared public URL with your father-in-law
- [ ] Created a README or documentation for end users

## Troubleshooting

If something isn't working:

1. **Check Render Logs**: Dashboard → Web Service → **Logs**
2. **Common Issues**:
   - ❌ "Connection refused": Make sure `PG_DSN` is the **Internal** URL
   - ❌ "Module not found": Run `pip install -r requirements.txt` locally to verify
   - ❌ "5xx errors": Check logs tab, usually a missing env var or database issue
3. **Reset**: You can manually redeploy from Render dashboard
4. **Need Help**: Read [DEPLOY_RENDER.md](DEPLOY_RENDER.md) or check Render docs

## Success Criteria

✅ All of the following are true:
- [ ] App is accessible at `https://fundraising-webapp.onrender.com` (or your custom domain)
- [ ] Homepage loads without errors
- [ ] Data from PostgreSQL is visible
- [ ] Database backup is enabled
- [ ] Logs show no errors in production

---

## Support Resources

- **Quick Start**: [RENDER_QUICKSTART.md](RENDER_QUICKSTART.md)
- **Full Guide**: [DEPLOY_RENDER.md](DEPLOY_RENDER.md)
- **Render Docs**: https://render.com/docs
- **Render Status**: https://status.render.com

---

## Cost Summary

| Component | Monthly Cost | Plan |
|-----------|-------------|------|
| Web Service | $7 | Standard |
| PostgreSQL | $15 | Standard |
| **Total** | **$22** | Production |

Free tier available for testing (0.5GB database limit).

---

**You're deploying a real product to production.** When this checklist is complete, your app is live on the internet and your team can use it immediately. 🎉
