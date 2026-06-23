"""Business Brain and account settings routes."""

from flask import Blueprint, redirect, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash

import db
from auth import current_business, current_user, login_required

bp = Blueprint("settings", __name__)


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    biz = current_business()
    saved = False
    if request.method == "POST":
        fields = {k: (request.form.get(k) or "").strip() for k in
                  ("name", "trade", "service_area", "owner_name", "brand_voice",
                   "services", "target_customer", "differentiators", "capacity_note",
                   "google_review_link", "mailing_address")}
        db.update_business(biz["id"], fields)
        biz = current_business()
        saved = True
    return render_template("settings.html", business=biz, saved=saved)


@bp.route("/settings/password", methods=["POST"])
@login_required
def settings_password():
    u = current_user()
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    if (check_password_hash(u["password_hash"], current) and len(new) >= 8):
        db.update_user_password(u["id"], generate_password_hash(new))
        return redirect("/settings?pw=ok")
    return redirect("/settings?pw=err")
