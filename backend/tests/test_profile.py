"""Self-service profile: only the owner, only name/phone/photo, enforced by the backend."""
import pytest

from app.models import User
from tests.workflow_fixtures import world  # noqa: F401

PROFILE = "/api/v1/profile"
PHOTO = f"{PROFILE}/photo"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def upload(client, world, who, data, content_type="image/png"):
    return client.put(PHOTO, content=data, headers={**world.h(who), "Content-Type": content_type})


def test_profile_shows_own_data_with_read_only_fields(client, world):
    body = client.get(PROFILE, headers=world.h("student")).json()
    assert body["email"] == world.users["student"].email
    assert body["role"] == "student" and body["is_active"] is True
    assert body["department"]["code"] == "MCA"
    assert body["phone"] is None and body["has_photo"] is False
    assert body["editable_fields"] == ["name", "phone", "photo"]


@pytest.mark.parametrize("who", ["student", "teaching", "authority", "admin"])
def test_user_can_update_name_and_phone_and_it_persists(client, db, world, who):
    r = client.patch(PROFILE, json={"name": "  New   Name ", "phone": "+91 98450 12345"}, headers=world.h(who))
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["phone"]) == ("New Name", "+91 98450 12345")
    db.expire_all()
    stored = db.get(User, world.users[who].id)
    assert (stored.name, stored.phone) == ("New Name", "+91 98450 12345")
    assert client.patch(PROFILE, json={"phone": ""}, headers=world.h(who)).json()["phone"] is None


@pytest.mark.parametrize("field,value", [
    ("role", "admin"), ("email", "other@safespeak.test"), ("department_id", 2), ("is_active", False),
    ("authority_level", 4), ("permissions", ["manage_users"]), ("id", 1), ("user_id", 1), ("photo_filename", "../x"),
])
def test_protected_fields_cannot_be_changed(client, db, world, field, value):
    before = db.get(User, world.users["student"].id)
    snapshot = (before.role, before.email, before.department_id, before.is_active, before.authority_level, before.photo_filename)
    r = client.patch(PROFILE, json={field: value}, headers=world.h("student"))
    assert r.status_code == 422
    db.expire_all()
    after = db.get(User, world.users["student"].id)
    assert (after.role, after.email, after.department_id, after.is_active, after.authority_level, after.photo_filename) == snapshot


def test_teaching_staff_cannot_promote_themselves(client, db, world):
    assert client.patch(PROFILE, json={"name": "T", "role": "higher_authority"}, headers=world.h("teaching")).status_code == 422
    db.expire_all()
    assert db.get(User, world.users["teaching"].id).role == "teaching_staff"
    # The permission set returned to the UI still follows the stored role.
    assert "review_complaints" not in client.get("/api/v1/auth/me", headers=world.h("teaching")).json()["permissions"]


@pytest.mark.parametrize("payload", [{"name": "x"}, {"name": "x" * 121}, {"phone": "abc"}, {"phone": "12"}, {"phone": "+91 <script>"}])
def test_invalid_values_are_rejected(client, world, payload):
    assert client.patch(PROFILE, json=payload, headers=world.h("student")).status_code == 422


def test_profile_requires_authentication(client):
    assert client.get(PROFILE).status_code == 401
    assert client.patch(PROFILE, json={"name": "Someone"}).status_code == 401
    assert client.put(PHOTO, content=PNG, headers={"Content-Type": "image/png"}).status_code == 401
    assert client.get(PHOTO).status_code == 401


@pytest.mark.parametrize("data,content_type,expected", [(PNG, "image/png", "image/png"), (JPEG, "image/jpeg", "image/jpeg"),
                                                       (WEBP, "image/webp", "image/webp")])
def test_photo_upload_and_owner_only_download(client, settings, world, data, content_type, expected):
    r = upload(client, world, "student", data, content_type)
    assert r.status_code == 200 and r.json()["has_photo"] is True
    assert client.get("/api/v1/auth/me", headers=world.h("student")).json()["has_photo"] is True

    got = client.get(PHOTO, headers=world.h("student"))
    assert got.status_code == 200 and got.content == data
    assert got.headers["content-type"] == expected and "no-store" in got.headers["cache-control"]
    # Stored on disk with a generated name, not in the database.
    files = list((settings.media_dir / "profile_photos").iterdir())
    assert len(files) == 1 and files[0].read_bytes() == data and files[0].name.startswith(f"{world.users['student'].id}-")
    # Another user only ever gets their own (missing) photo: there is no way to address someone else's.
    assert client.get(PHOTO, headers=world.h("student2")).status_code == 404


def test_replacing_and_deleting_photo_removes_old_files(client, settings, world):
    upload(client, world, "student", PNG)
    upload(client, world, "student", JPEG, "image/jpeg")
    folder = settings.media_dir / "profile_photos"
    assert [f.suffix for f in folder.iterdir()] == [".jpg"]
    r = client.delete(PHOTO, headers=world.h("student"))
    assert r.status_code == 200 and r.json()["has_photo"] is False
    assert list(folder.iterdir()) == []
    assert client.get(PHOTO, headers=world.h("student")).status_code == 404


@pytest.mark.parametrize("data", [
    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    b"GIF89a" + b"\x00" * 20,
    b"%PDF-1.7 not an image",
    b"MZ\x90\x00 executable",
    b"",
])
def test_unsupported_or_malformed_uploads_are_rejected(client, settings, world, data):
    # Even when the header claims an image type.
    r = upload(client, world, "student", data, "image/png")
    assert r.status_code in (415, 422)
    assert not (settings.media_dir / "profile_photos").exists() or not any((settings.media_dir / "profile_photos").iterdir())


def test_oversized_upload_is_rejected(client, settings, world):
    big = PNG + b"\x00" * settings.profile_photo_max_bytes
    assert upload(client, world, "student", big).status_code == 413
    assert client.get(PROFILE, headers=world.h("student")).json()["has_photo"] is False


def test_phone_and_photo_are_not_exposed_to_other_users(client, world):
    client.patch(PROFILE, json={"phone": "+91 98450 12345"}, headers=world.h("student"))
    upload(client, world, "student", PNG)
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = client.post("/api/v1/concerns", json={"description": "The hostel mess food has been cold for a week."},
                       headers=world.h("student")).json()["complaint_id"]
    seen = [
        client.get(f"/api/v1/concerns/{code}", headers=world.h("authority")).text,
        client.get("/api/v1/concerns", headers=world.h("admin")).text,
        client.get("/api/v1/admin/users", headers=world.h("admin")).text,
    ]
    for text in seen:
        assert "98450" not in text and "photo_filename" not in text
