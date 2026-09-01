"""Production deployment settings.

Edit this file once before building the public launcher. The Supabase key here must
be a publishable/anon key only. Never put a service_role or sb_secret key here.
"""

SUPABASE_URL = "https://ttyunqjbikrfnabrthva.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_n9zb4b5bL_2B5tXJtp4juw_5a6j0Xh5"
CATALOG_ID = 1
ADMIN_PANEL_URL = "mizu-launcher-admin-panel.vercel.app"
# Educational DRM key. It is not a secret against a determined reverse engineer.
# Use a unique long random value for your project and ship the same value with each game.
DRM_MASTER_SECRET = "MizuDEV56"

# Global launcher update control. Host a JSON manifest at this URL.
# Example manifest:
# {"latest_version":"1.1.0","download_url":"https://example.com/mizulauncher","message":"Nowa wersja jest wymagana."}
UPDATE_MANIFEST_URL = ""
UPDATE_DOWNLOAD_URL = ""
UPDATE_ID = 1
UPDATE_CHECK_ENABLED = True
