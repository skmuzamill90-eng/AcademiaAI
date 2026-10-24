"""Real tokens, real JSON and per-institution CSVs; no authentication overrides."""
import json
import time
import pytest
from fastapi.testclient import TestClient
from app import auth
from app.main import _production_secret_is_usable, create_app
from scripts import saas_admin
from scripts.saas_admin import bootstrap

PASSWORD = 'Unique-test-password-2026!'

@pytest.mark.parametrize('secret', [
    auth.DEFAULT_SECRET_WARNING,
    'REPLACE_WITH_OUTPUT_OF_SECRET_GENERATOR',
    'short-secret',
])
def test_production_rejects_missing_placeholder_or_short_auth_secret(secret):
    assert not _production_secret_is_usable(secret)


def test_production_accepts_long_configured_auth_secret():
    assert _production_secret_is_usable('a' * 48)

def login(client, username, password=PASSWORD):
    r = client.post('/api/auth/login', data={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['access_token']}

@pytest.fixture()
def saas(tmp_path):
    bootstrap('owner', PASSWORD)
    with auth.transaction() as d:
        d['users']['owner']['must_change_password'] = False
    with TestClient(create_app(str(tmp_path / 'datasets'))) as c:
        owner = login(c, 'owner')
        tenants, admins = [], []
        for key in ('alpha', 'bravo'):
            r = c.post('/api/platform/institutions', headers=owner, json={
                'name': key + ' College', 'contact_email': key + '@example.edu',
                'admin_username': key, 'status': 'active'})
            assert r.status_code == 201, r.text
            iid = r.json()['data']['id']; tenants.append(iid)
            token = c.post(f'/api/platform/institutions/{iid}/administrator/setup', headers=owner).json()['data']['setup_token']
            assert c.post('/api/auth/setup', json={'token': token, 'new_password': PASSWORD}).status_code == 200
            admins.append(login(c, key))
        c.owner, c.admins, c.tenants = owner, admins, tenants
        yield c


def add_student(c, headers, sid='STU90000001', name='Private Alpha'):
    r = c.post('/api/students', headers=headers, json={'student_id': sid, 'student_name': name,
        'department': 'CSE', 'year_of_study': 1, 'section': 'A', 'admission_year': 2026,
        'student_email': sid.lower() + '@example.edu', 'cgpa': 8.5, 'overall_attendance_pct': 92})
    assert r.status_code == 201, r.text
    return r.json()['data']


def student_login(c, sid='STU90000001', username='learner'):
    r = c.post('/api/institution/accounts', headers=c.admins[0], json={'student_id': sid, 'username': username})
    assert r.status_code == 201, r.text
    token = c.post(f'/api/institution/accounts/{username}/setup', headers=c.admins[0]).json()['data']['setup_token']
    assert c.post('/api/auth/setup', json={'token': token, 'new_password': PASSWORD}).status_code == 200
    return login(c, username)


def test_login_hashing_failed_login_and_bootstrap_once(saas):
    c = saas
    assert c.post('/api/auth/login', data={'username': 'owner', 'password': PASSWORD, 'login_type': 'campus'}).status_code == 401
    assert c.post('/api/auth/login', data={'username': 'alpha', 'password': PASSWORD, 'login_type': 'admin'}).status_code == 401
    assert c.post('/api/auth/login', data={'username': 'owner', 'password': PASSWORD, 'login_type': 'admin'}).status_code == 200
    assert c.post('/api/auth/login', data={'username': 'alpha', 'password': PASSWORD, 'login_type': 'campus'}).status_code == 200
    assert c.post('/api/auth/login', data={'username': 'alpha', 'password': 'wrong'}).status_code == 401
    assert c.post('/api/auth/login', data={'username': 'missing', 'password': 'wrong'}).status_code == 401
    stored = auth._read_users()['alpha']
    assert stored['password_hash'] != PASSWORD and auth._verify_password(PASSWORD, stored['password_hash'])
    with pytest.raises(ValueError):
        bootstrap('another_owner', PASSWORD)
    assert 'another_owner' not in auth._read_users()
    assert c.get('/api/auth/me', headers=c.admins[0]).json()['data']['role'] == 'college_admin'


def test_bootstrap_super_admin_cli_command(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, 'USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr(saas_admin, 'get_data_dir', lambda: tmp_path / 'data')
    monkeypatch.setattr(saas_admin.sys, 'argv', [
        'saas_admin.py', 'bootstrap-super-admin', '--username', 'platform_owner'])
    passwords = iter((PASSWORD, PASSWORD))
    monkeypatch.setattr(saas_admin.getpass, 'getpass', lambda _: next(passwords))

    saas_admin.main()

    assert auth._read_users()['platform_owner']['role'] == 'super_admin'


def test_college_isolation_duplicate_ids_crud_and_analytics(saas):
    c = saas; a, b = c.admins
    add_student(c, a)
    add_student(c, b, name='Private Bravo')
    add_student(c, b, sid='STU90000002')
    assert c.get('/api/students/STU90000001', headers=a).json()['data']['personal']['student_name'] == 'Private Alpha'
    assert c.get('/api/students/STU90000002', headers=a).status_code == 404
    assert c.patch('/api/students/STU90000002', headers=a, json={'student_name': 'Hacked'}).status_code == 404
    assert c.get('/api/dashboard/summary', headers=a).json()['data']['total_students'] == 1
    assert c.get('/api/dashboard/summary', headers=b).json()['data']['total_students'] == 2
    assert c.get('/api/students', headers=a, params={'institution_id': c.tenants[1]}).json()['meta']['total'] == 1
    r = c.patch('/api/students/STU90000001', headers=a, json={'institution_id': c.tenants[1], 'student_name': 'Changed Alpha'})
    assert r.status_code in (200, 422)
    assert c.get('/api/students/STU90000001', headers=b).json()['data']['personal']['student_name'] == 'Private Bravo'
    assert c.get('/api/platform/institutions', headers=a).status_code == 403
    assert c.post('/api/platform/institutions', headers=a, json={'name': 'Evil', 'admin_username': 'evil', 'contact_email': 'e@e.edu'}).status_code == 403
    assert c.post('/api/auth/users', headers=a, json={'username': 'evil', 'password': PASSWORD, 'role': 'super_admin'}).status_code == 403
    assert c.patch('/api/institution', headers=a, json={'name': 'Evil', 'contact_email': 'e@e.edu', 'role': 'super_admin'}).status_code == 422
    assert c.get('/api/students', headers=c.owner).status_code == 403


def test_student_self_only_and_forbidden_routes(saas):
    c = saas
    add_student(c, c.admins[0]); add_student(c, c.admins[0], 'STU90000003')
    assert c.post('/api/institution/accounts', headers=c.admins[0], json={
        'username': 'specialid', 'student_id': 'STU.90000001/EXT',
    }).status_code == 404
    first_iv = c.post('/api/interventions', headers=c.admins[0], json={
        'student_id': 'STU90000001', 'intervention_type': 'Mentoring',
        'assigned_date': '2026-10-24', 'status': 'Assigned',
        'follow_up_notes': 'Private staff-only note',
    })
    second_iv = c.post('/api/interventions', headers=c.admins[0], json={
        'student_id': 'STU90000003', 'intervention_type': 'Academic tutoring',
        'assigned_date': '2026-10-24', 'status': 'Recommended',
        'follow_up_notes': 'Another student private note',
    })
    assert first_iv.status_code == 201 and second_iv.status_code == 201
    h = student_login(c)
    profile = c.get('/api/student/me?student_id=STU90000003&institution_id=attacker', headers=h)
    assert profile.status_code == 200 and profile.json()['data']['student_id'] == 'STU90000001'
    interventions = profile.json()['data']['interventions']
    assert len(interventions) == 1 and interventions[0]['intervention_id'] == first_iv.json()['data']['intervention_id']
    assert interventions[0]['status'] == 'Assigned'
    assert 'follow_up_notes' not in interventions[0]
    assert 'risk' in profile.json()['data']
    assert 'faculty_feedback_1_to_5' not in profile.json()['data']['feedback']
    student_login_response = c.post('/api/auth/login', data={
        'username': 'learner', 'password': PASSWORD, 'login_type': 'student',
    })
    assert student_login_response.status_code == 200
    assert student_login_response.json()['user']['role'] == 'student'
    assert c.post('/api/auth/login', data={
        'username': 'learner', 'password': PASSWORD, 'login_type': 'campus',
    }).status_code == 401
    assert c.post('/api/auth/login', data={
        'username': 'learner', 'password': PASSWORD, 'login_type': 'admin',
    }).status_code == 401
    assert c.post('/api/auth/login', data={
        'username': 'alpha', 'password': PASSWORD, 'login_type': 'student',
    }).status_code == 401
    for path in ['/api/students', '/api/students/STU90000003', '/api/students/STU90000001', '/api/dashboard/summary',
                 '/api/analytics/departments', '/api/metadata', '/api/interventions', '/api/imports/config',
                 '/api/platform/overview', '/api/institution/accounts', '/api/predictions/evaluation',
                 '/api/students/STU90000001/predictions']:
        assert c.get(path, headers=h).status_code == 403, path
    assert c.post('/api/ai/chat', headers=h, json={'message': 'hello'}).status_code == 403
    assert c.post('/api/institution/accounts', headers=c.admins[0], json={'username': 'duplicate', 'student_id': 'STU90000001'}).status_code == 409


def test_suspension_and_revocation_do_not_revive_old_tokens(saas):
    c = saas; add_student(c, c.admins[0]); student = student_login(c)
    path = f'/api/platform/institutions/{c.tenants[0]}'
    assert c.patch(path, headers=c.owner, json={'status': 'suspended'}).status_code == 200
    for h in (c.admins[0], student):
        assert c.get('/api/auth/me', headers=h).status_code == 401
    assert c.post('/api/auth/login', data={'username': 'alpha', 'password': PASSWORD}).status_code == 401
    assert c.get('/api/dashboard/summary', headers=c.admins[1]).status_code == 200
    assert c.patch(path, headers=c.owner, json={'status': 'active'}).status_code == 200
    assert c.get('/api/dashboard/summary', headers=c.admins[0]).status_code == 401
    fresh = login(c, 'alpha')
    assert c.post('/api/auth/logout', headers=fresh).status_code == 200
    assert c.get('/api/auth/me', headers=fresh).status_code == 401


def test_setup_one_use_expiry_reset_and_password_change(saas):
    c = saas; path = f'/api/platform/institutions/{c.tenants[0]}/administrator/setup'
    token = c.post(path, headers=c.owner).json()['data']['setup_token']
    assert c.get('/api/auth/me', headers=c.admins[0]).status_code == 401
    h = login(c, 'alpha')
    assert c.get('/api/dashboard/summary', headers=h).status_code == 403
    r = c.post('/api/auth/setup', json={'token': token, 'new_password': PASSWORD + 'new'})
    assert r.status_code == 200
    assert c.post('/api/auth/setup', json={'token': token, 'new_password': PASSWORD}).status_code == 400
    h = login(c, 'alpha', PASSWORD + 'new')
    assert c.post('/api/auth/password', headers=h, json={'current_password': PASSWORD + 'new', 'new_password': PASSWORD + 'newer'}).status_code == 200
    assert c.get('/api/auth/me', headers=h).status_code == 401
    token = c.post(path, headers=c.owner).json()['data']['setup_token']
    with auth.transaction() as data:
        data['users']['alpha']['setup_expires'] = time.time() - 1
    assert c.post('/api/auth/setup', json={'token': token, 'new_password': PASSWORD}).status_code == 400
    logs = c.get('/api/platform/audit', headers=c.owner).text
    assert token not in logs and PASSWORD not in logs and 'password_hash' not in logs


def test_import_ownership_and_tenant_commit(saas):
    c = saas; a, b = c.admins
    content = b'student_id,student_name,department,year_of_study,section,admission_year,student_email\nSTU90000004,Imported Alpha,CSE,1,A,2026,imported@example.edu\n'
    r = c.post('/api/imports/uploads', headers=a, files={'file': ('students.csv', content, 'text/csv')})
    assert r.status_code == 201, r.text
    upload = r.json()['data']
    uid = upload['upload_id']
    assert c.get(f'/api/imports/uploads/{uid}/rows', headers=b).status_code == 404
    config = c.get('/api/imports/config', headers=a).json()['data']
    mode = 'insert_only'
    r = c.post(f'/api/imports/uploads/{uid}/import', headers=a, json={'mode': mode, 'mapping': {k: v['column'] for k, v in upload['suggested_mapping'].items() if v.get('column') is not None}, 'institution_id': c.tenants[1]})
    assert r.status_code == 202, r.text
    job = r.json()['data']['job_id']
    for _ in range(100):
        result = c.get(f'/api/imports/jobs/{job}', headers=a).json()['data']
        if result['status'] in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(.02)
    assert result['status'] == 'completed', result
    assert c.get('/api/students/STU90000004', headers=a).status_code == 200
    assert c.get('/api/students/STU90000004', headers=b).status_code == 404
    assert c.get(f'/api/imports/jobs/{job}', headers=b).status_code == 404


def test_legacy_unmapped_data_and_identity_are_not_exposed(tmp_path):
    auth.USERS_FILE.write_text(json.dumps({'legacy': {'username': 'legacy', 'role': 'admin', 'active': True,
                                                       'password_hash': auth._hash_password(PASSWORD)}}))
    assert auth.authenticate_user('legacy', PASSWORD) is None
    assert 'legacy' in auth.read_store()['users']
    with TestClient(create_app(str(tmp_path / 'legacy'))) as c:
        assert c.get('/api/students').status_code == 401
        assert c.get('/api/metadata').status_code == 401
        assert 'student_count' not in c.get('/api/health').text


def test_rate_limit_and_tampered_token(saas):
    c = saas
    h = dict(c.owner); h['Authorization'] += 'tampered'
    assert c.get('/api/auth/me', headers=h).status_code == 401
    for _ in range(10):
        c.post('/api/auth/login', data={'username': 'missing', 'password': 'wrong'})
    assert c.post('/api/auth/login', data={'username': 'missing', 'password': 'wrong'}).status_code == 429
