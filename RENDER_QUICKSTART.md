# 🚀 Render Deployment - Quick Start

Get your app live in **3 simple steps** (no local setup needed).

## Step 1: Push to GitHub (5 minutes)

If you haven't already:

```bash
# One-time setup
git remote add origin https://github.com/YOUR_USERNAME/fundraising-leads-pipeline.git
git branch -M main
git push -u origin main
```

Or if using GitHub CLI:
```bash
gh repo create fundraising-leads-pipeline --public --source=. --remote=origin --push
```

## Step 2: Set Up PostgreSQL Database (5 minutes)

1. Go to [render.com](https://render.com) → Sign up (free)
2. Click **New +** → **PostgreSQL**
3. Fill in:
   - **Name**: `fundraising-db`
   - **Database**: `fundraising`
   - **Region**: (pick closest to you)
4. Click **Create Database**
5. Once created, copy the **Internal Database URL** (blue button labeled "Internal")
   - Save this; you'll need it in Step 3

## Step 3: Deploy the Web App (5 minutes)

1. Click **New +** → **Web Service**
2. Select your GitHub repo `fundraising-leads-pipeline`
3. Fill in:
   - **Name**: `fundraising-webapp`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn webapp.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Standard ($7/mo) or Free
4. Click **Advanced** and add **Environment Variables**:
   ```
   PG_DSN = [paste your Internal Database URL from Step 2]
   ANTHROPIC_API_KEY = [paste your API key from https://console.anthropic.com]
   LLM_MODEL = claude-opus-5
   USER_AGENT = FundraisingProspectEngine/0.1
   PYTHONUNBUFFERED = 1
   ```
5. Click **Create Web Service**

**Wait 3-5 minutes for deployment...**

## Done! 🎉

Render will give you a public URL like `https://fundraising-webapp.onrender.com`. Your app is live!

## Next: Load Your Data

Your database is empty. To populate it, run the ingest pipeline **locally** against the Render database:

```bash
# Update .env with Render's PG_DSN
export PG_DSN="postgres://user:pass@hostname:5432/fundraising"

# Run the ingest phases
python -m ingest.phase1_nces
python -m ingest.phase2_dpi
# ... etc
```

Or use this one-liner to load all phases:
```bash
for phase in 1 2 3 4 4b 5 6 7; do
  python -m ingest.phase$phase && echo "✅ Phase $phase done"
done
```

## Troubleshooting

**Deploy failed?**
- Check **Logs** tab in Render Dashboard
- Common issues:
  - Python version mismatch (should be 3.11)
  - Missing environment variables
  - `requirements.txt` syntax error

**"Connection refused" error in app?**
- Make sure `PG_DSN` is the **Internal** database URL, not the external one
- Database must be in the same region as the web service

**Still stuck?**
- Read [DEPLOY_RENDER.md](DEPLOY_RENDER.md) for detailed instructions
- Check [Render Docs](https://render.com/docs)

## Costs

- **Web Service**: $7/month (Standard) or $0 (Free tier)
- **Database**: $15/month (Standard) or $0 (Free tier, 0.5GB limit)
- **Total**: ~$22/month for production

Free tier works for testing but not recommended for daily use.

---

**Your app is now public at `https://fundraising-webapp.onrender.com`** ✨
