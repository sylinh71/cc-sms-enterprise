from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
import os
import io
import csv

app = FastAPI(title="CC TEAM - SMS | Master Schedule Enterprise Edition V3.8 (Strict 3-Tier Separation)")

DB_FILE = "local_db.json"

CHANNELS = ["Call (VNP)", "Chat (VNP)", "Xử lý MXH", "Email", "KHL", "TikTok", "Youtube", "Outbound", "Giám sát_IB", "Giám sát_OB"]
DAYS_OF_WEEK = [
    {"key": "Mon", "name": "Thứ Hai"},
    {"key": "Tue", "name": "Thứ Ba"},
    {"key": "Wed", "name": "Thứ Tư"},
    {"key": "Thu", "name": "Thứ Năm"},
    {"key": "Fri", "name": "Thứ Sáu"},
    {"key": "Sat", "name": "Thứ Bảy"},
    {"key": "Sun", "name": "Chủ Nhật"}
]

def get_default_matrix():
    matrix = {}
    hours = list(range(7, 21))
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        matrix[day] = {}
        for chan in CHANNELS:
            matrix[day][chan] = {}
            for h in hours:
                base_req = 3 if h in [9, 10, 14, 15] and ("Call" in chan or "Chat" in chan) else (2 if "Call" in chan or "Chat" in chan else 1)
                matrix[day][chan][str(h)] = {"min": base_req, "target": base_req + 1}
    return matrix

def generate_enterprise_schedule(db):
    schedule = {}
    active_users = [u for u in db["users"] if u["status"] == "ACTIVE" and u["role"] != "ADMIN"]
    skills_db = db["skills"]
    matrix = db["matrix_v3"]
    hours = list(range(7, 21))

    for day_obj in DAYS_OF_WEEK:
        d_key = day_obj["key"]
        schedule[d_key] = {}
        for u in active_users:
            schedule[d_key][u["id"]] = {str(h): "OFF" for h in hours}

    admin_users = [u for u in db["users"] if u["role"] == "ADMIN"]
    for day_obj in DAYS_OF_WEEK:
        d_key = day_obj["key"]
        for u in admin_users:
            if d_key not in schedule: schedule[d_key] = {}
            schedule[d_key][u["id"]] = {str(h): "ADMIN_OVERLORD" for h in hours}

    for day_obj in DAYS_OF_WEEK:
        d_key = day_obj["key"]
        day_matrix = matrix.get(d_key, matrix.get("Mon"))
        peak_hours = [9, 10, 11, 14, 15, 16, 7, 8, 12, 13, 17, 18, 19, 20]
        sorted_hours = [h for h in peak_hours if h in hours]

        for h in sorted_hours:
            h_str = str(h)
            for chan in CHANNELS:
                req_data = day_matrix.get(chan, {}).get(h_str, {"min": 1})
                needed_count = req_data.get("min", 1)
                assigned_in_cell = 0
                
                def get_daily_hours(emp_id):
                    return sum(1 for hr in hours if schedule[d_key][emp_id][str(hr)] not in ["OFF", "BREAK", "ADMIN_OVERLORD"])

                sorted_users = sorted(active_users, key=lambda x: get_daily_hours(x["id"]))

                for u in sorted_users:
                    if assigned_in_cell >= needed_count: break
                    emp_id = u["id"]
                    if get_daily_hours(emp_id) >= 8: continue

                    emp_skill = next((sk for sk in skills_db if sk["employee_id"] == emp_id), None)
                    has_skill = False
                    if emp_skill:
                        if any(s.upper() in chan.upper() for s in emp_skill["skills"]) or "ALL" in emp_skill["skills"]:
                            has_skill = True
                    if not has_skill: continue

                    emp_schedule = schedule[d_key][emp_id]
                    if emp_schedule[h_str] == "OFF":
                        emp_schedule[h_str] = chan
                        assigned_in_cell += 1

    return schedule

DEFAULT_DATA = {
    "users": [
        {"id": "EMP01", "username": "linhls", "full_name": "Lê Sỹ Linh", "password": "123", "role": "ADMIN", "scope": "Global", "status": "ACTIVE", "team": "Ban Giám Đốc"},
        {"id": "EMP02", "username": "sup_nam", "full_name": "Trần Văn Nam", "password": "123", "role": "SUPERVISOR", "scope": "Team CSKH", "status": "ACTIVE", "team": "Team CSKH 1"},
        {"id": "EMP03", "username": "agent_a", "full_name": "Nguyễn Văn A", "password": "123", "role": "USER", "scope": "Cá nhân", "status": "ACTIVE", "team": "Team CSKH 1"},
        {"id": "EMP04", "username": "agent_b", "full_name": "Trần Thị B", "password": "123", "role": "USER", "scope": "Cá nhân", "status": "INACTIVE", "team": "Team CSKH 2"}
    ],
    "skills": [
        {"id": "SK-01", "employee_id": "EMP03", "employee": "Nguyễn Văn A", "skills": ["CALL", "CHAT", "VIP"], "level": "Senior"},
        {"id": "SK-02", "employee_id": "EMP02", "employee": "Trần Văn Nam", "skills": ["CALL", "CHAT", "KHL"], "level": "Expert"}
    ],
    "matrix_v3": get_default_matrix(),
    "master_schedule": {
        "status": "PUBLISHED",
        "week_title": "Tuần 38 (14/09/2026 - 20/09/2026)",
        "data": {}
    },
    "compliance": [
        {"rule_id": "RULE-01", "name": "Thời gian làm việc liên tục tối đa", "limit_value": "8 giờ/ngày", "action": "Chặn (BLOCK)"},
        {"rule_id": "RULE-02", "name": "Quyền sửa lịch ở trạng thái LOCKED", "limit_value": "Chỉ ADMIN mới được phép (Bắt buộc nhập lý do sự cố)", "action": "Chặn SUPERVISOR"}
    ],
    "handbook": [
        {"id": "HB-01", "title": "Quy chế phân quyền 3 tầng", "content": "Admin, Supervisor và User có không gian thao tác hoàn toàn biệt lập phục vụ đúng chuẩn vận hành tổng đài.", "updated_at": "2026-09-19 11:00"}
    ],
    "audit_logs": [
        {"id": "AUD-101", "actor": "linhls (ADMIN)", "action": "SYSTEM_V3.8_STRICT_SEPARATION", "target": "RBAC_ENGINE", "timestamp": "2026-09-19 11:00:00", "reason": "Phân tách rõ ràng giao diện và quyền hạn giữa Admin, Sup và User"}
    ]
}

def load_data():
    if not os.path.exists(DB_FILE):
        DEFAULT_DATA["master_schedule"]["data"] = generate_enterprise_schedule(DEFAULT_DATA)
        save_data(DEFAULT_DATA)
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "master_schedule" not in data or not data["master_schedule"]["data"]:
                data["master_schedule"]["data"] = generate_enterprise_schedule(data)
            return data
    except Exception:
        return DEFAULT_DATA

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class LoginPayload(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    id: str
    full_name: str
    password: str
    role: str
    status: str
    team: str

class UserUpdate(BaseModel):
    full_name: str
    role: str
    status: str
    team: str

class SkillUpdate(BaseModel):
    level: str
    skills: List[str]

class MatrixCellUpdateV3(BaseModel):
    day: str
    channel: str
    hour: int
    min_val: int
    target_val: int

class ScheduleUpdatePayload(BaseModel):
    day: str
    emp_id: str
    hour: int
    channel: str
    reason: Optional[str] = ""
    actor_role: Optional[str] = "ADMIN"

class StatusUpdatePayload(BaseModel):
    status: str

class HandbookNote(BaseModel):
    title: str
    content: str

@app.post("/api/v1/auth/login")
def login(payload: LoginPayload):
    db = load_data()
    user = next((u for u in db["users"] if u["username"] == payload.username and u["password"] == payload.password), None)
    if not user:
        raise HTTPException(status_code=400, detail="Sai tên đăng nhập hoặc mật khẩu!")
    if user["status"] == "INACTIVE":
        raise HTTPException(status_code=403, detail="Tài khoản này đã bị khóa!")
    return {"success": True, "user": user}

@app.get("/api/v1/admin/users")
def get_users(): return load_data()["users"]

@app.post("/api/v1/admin/users")
def create_user(data: UserCreate):
    db = load_data()
    for u in db["users"]:
        if u["id"] == data.id: raise HTTPException(status_code=400, detail="Mã nhân sự đã tồn tại!")
    scope_map = {"ADMIN": "Global", "SUPERVISOR": "Team CSKH", "USER": "Cá nhân"}
    role_upper = data.role.upper()
    new_user = {
        "id": data.id, "username": data.id, "full_name": data.full_name,
        "password": data.password, "role": role_upper,
        "scope": scope_map.get(role_upper, "Cá nhân"),
        "status": data.status.upper(), "team": data.team
    }
    db["users"].append(new_user)
    if role_upper != "ADMIN":
        if not any(sk["employee_id"] == data.id for sk in db["skills"]):
            db["skills"].append({"id": f"SK-0{len(db['skills'])+1}", "employee_id": data.id, "employee": data.full_name, "skills": ["CHAT"], "level": "Junior"})
    db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "CREATE_USER", "target": data.id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Thêm nhân sự {data.full_name}"})
    save_data(db)
    return {"success": True, "users": db["users"]}

@app.put("/api/v1/admin/users/{emp_id}")
def update_user(emp_id: str, data: UserUpdate):
    db = load_data()
    for u in db["users"]:
        if u["id"] == emp_id:
            u["full_name"], u["role"], u["status"], u["team"] = data.full_name, data.role.upper(), data.status.upper(), data.team
            scope_map = {"ADMIN": "Global", "SUPERVISOR": "Team CSKH", "USER": "Cá nhân"}
            u["scope"] = scope_map.get(data.role.upper(), "Cá nhân")
            if data.role.upper() == "ADMIN":
                db["skills"] = [sk for sk in db["skills"] if sk["employee_id"] != emp_id]
            for sk in db["skills"]:
                if sk["employee_id"] == emp_id: sk["employee"] = data.full_name
            db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "UPDATE_USER", "target": emp_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Cập nhật user {emp_id}"})
            save_data(db)
            return {"success": True, "users": db["users"]}
    raise HTTPException(status_code=404, detail="Không tìm thấy.")

@app.delete("/api/v1/admin/users/{emp_id}")
def delete_user(emp_id: str):
    db = load_data()
    for u in db["users"]:
        if u["id"] == emp_id:
            u["status"] = "INACTIVE"
            db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "SOFT_DELETE_USER", "target": emp_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Khóa nhân sự {emp_id}"})
            save_data(db)
            return {"success": True, "users": db["users"]}
    raise HTTPException(status_code=404, detail="Không tìm thấy.")

@app.post("/api/v1/admin/users/{emp_id}/restore")
def restore_user(emp_id: str):
    db = load_data()
    for u in db["users"]:
        if u["id"] == emp_id:
            u["status"] = "ACTIVE"
            db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "RESTORE_USER", "target": emp_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Khôi phục nhân sự {emp_id}"})
            save_data(db)
            return {"success": True, "users": db["users"]}
    raise HTTPException(status_code=404, detail="Không tìm thấy.")

@app.get("/api/v1/admin/users/template-csv")
def download_user_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MaNV", "HoTen", "MatKhau", "VaiTro", "TrangThai", "Team"])
    writer.writerow(["EMP05", "Nguyễn Văn E", "123456", "USER", "ACTIVE", "Team CSKH 1"])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=Mau_import_nhan_su.csv"})

@app.post("/api/v1/admin/users/import-csv")
async def import_users_csv(file: UploadFile = File(...)):
    contents = await file.read()
    decoded = contents.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(decoded))
    next(reader, None)
    db = load_data()
    count = 0
    scope_map = {"ADMIN": "Global", "SUPERVISOR": "Team CSKH", "USER": "Cá nhân"}
    for row in reader:
        if len(row) >= 6:
            emp_id, full_name, password, role, status, team = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip().upper(), row[4].strip().upper(), row[5].strip()
            existing = next((u for u in db["users"] if u["id"] == emp_id), None)
            if not existing:
                db["users"].append({
                    "id": emp_id, "username": emp_id, "full_name": full_name,
                    "password": password, "role": role, "scope": scope_map.get(role, "Cá nhân"),
                    "status": status, "team": team
                })
                if role != "ADMIN":
                    db["skills"].append({"id": f"SK-0{len(db['skills'])+1}", "employee_id": emp_id, "employee": full_name, "skills": ["CHAT"], "level": "Junior"})
                count += 1
    db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "IMPORT_USERS_CSV", "target": f"{count} users", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Import {count} nhân sự"})
    save_data(db)
    return {"success": True, "message": f"Đã import thành công {count} nhân sự!", "users": db["users"]}

@app.get("/api/v1/admin/export-csv")
def export_users_csv():
    db = load_data()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MaNV", "HoTen", "VaiTro", "PhamVi", "TrangThai", "Team"])
    for u in db["users"]: writer.writerow([u["id"], u["full_name"], u["role"], u["scope"], u["status"], u["team"]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=Danh_sach_nhan_su.csv"})

@app.get("/api/v1/admin/skills")
def get_skills(): return load_data()["skills"]

@app.put("/api/v1/admin/skills/{skill_id}")
def update_skill(skill_id: str, data: SkillUpdate):
    db = load_data()
    for sk in db["skills"]:
        if sk["id"] == skill_id:
            sk["level"], sk["skills"] = data.level, data.skills
            db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "UPDATE_SKILL", "target": skill_id, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Cập nhật kỹ năng {sk['employee']}"})
            save_data(db)
            return {"success": True, "skills": db["skills"]}
    raise HTTPException(status_code=404, detail="Không tìm thấy.")

@app.get("/api/v1/admin/matrix-v3")
def get_matrix_v3():
    db = load_data()
    return {"channels": CHANNELS, "days": DAYS_OF_WEEK, "hours": list(range(7, 21)), "matrix": db["matrix_v3"]}

@app.post("/api/v1/admin/matrix-v3/update-cell")
def update_matrix_cell_v3(data: MatrixCellUpdateV3):
    db = load_data()
    if data.day in db["matrix_v3"] and data.channel in db["matrix_v3"][data.day]:
        db["matrix_v3"][data.day][data.channel][str(data.hour)] = {"min": max(0, data.min_val), "target": max(data.min_val, data.target_val)}
        db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "UPDATE_MATRIX_V3", "target": f"{data.day}-{data.channel}@{data.hour}h", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Min:{data.min_val}, Target:{data.target_val}"})
        save_data(db)
        return {"success": True, "matrix": db["matrix_v3"]}
    raise HTTPException(status_code=400, detail="Lỗi tham số.")

@app.post("/api/v1/admin/matrix-v3/copy-template")
def copy_template_matrix(payload: dict):
    source_day = payload.get("source_day", "Mon")
    db = load_data()
    if source_day not in db["matrix_v3"]: raise HTTPException(status_code=400, detail="Ngày nguồn không tồn tại.")
    source_data = db["matrix_v3"][source_day]
    for d in db["matrix_v3"]:
        db["matrix_v3"][d] = json.loads(json.dumps(source_data))
    db["audit_logs"].insert(0, {"id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)", "action": "COPY_MATRIX_TEMPLATE", "target": f"From {source_day}", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": "Sao chép mẫu định biên tuần"})
    save_data(db)
    return {"success": True, "message": "📥 Đã sao chép mẫu định biên thành công cho cả tuần!", "matrix": db["matrix_v3"]}

@app.get("/api/v1/admin/schedule")
def get_schedule():
    db = load_data()
    if not db["master_schedule"]["data"]:
        db["master_schedule"]["data"] = generate_enterprise_schedule(db)
        save_data(db)
    return db["master_schedule"]

@app.post("/api/v1/admin/schedule/update-cell")
def update_schedule_cell(payload: ScheduleUpdatePayload):
    db = load_data()
    sched = db["master_schedule"]
    status = sched["status"]

    if status == "LOCKED":
        if payload.actor_role != "ADMIN":
            raise HTTPException(status_code=403, detail="⛔ Lịch đã bị KHÓA (LOCKED)! Supervisor không có quyền can thiệp. Chỉ Administrator mới được phép xử lý ngoại lệ thay thế sự cố.")
        if not payload.reason or not payload.reason.strip():
            raise HTTPException(status_code=400, detail="❌ Lịch đã LOCKED, bắt buộc phải nhập lý do ngoại lệ thay thế sự cố!")

    if status == "PUBLISHED" and (not payload.reason or not payload.reason.strip()):
        raise HTTPException(status_code=400, detail="❌ Lịch đã PUBLISHED, bắt buộc phải nhập lý do điều chỉnh ca trực!")

    if payload.day not in sched["data"]: sched["data"][payload.day] = {}
    if payload.emp_id not in sched["data"][payload.day]: sched["data"][payload.day][payload.emp_id] = {}
    sched["data"][payload.day][payload.emp_id][str(payload.hour)] = payload.channel
    
    reason_str = payload.reason if payload.reason else f"Cập nhật ca trực thủ công [{status}]"
    db["audit_logs"].insert(0, {
        "id": f"AUD-{len(db['audit_logs'])+1}", "actor": f"linhls ({payload.actor_role})",
        "action": f"SCHEDULE_EDIT [{status}]",
        "target": f"Ngày {payload.day} - NV {payload.emp_id} @ {payload.hour}h -> {payload.channel}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": reason_str
    })
    save_data(db)
    return {"success": True, "schedule": sched}

@app.post("/api/v1/admin/schedule/status")
def update_schedule_status(payload: StatusUpdatePayload):
    db = load_data()
    db["master_schedule"]["status"] = payload.status
    db["audit_logs"].insert(0, {
        "id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)",
        "action": "CHANGE_SCHEDULE_STATUS", "target": f"Chuyển trạng thái sang {payload.status}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": f"Cập nhật vòng đời lịch sang: {payload.status}"
    })
    save_data(db)
    return {"success": True, "schedule": db["master_schedule"]}

@app.post("/api/v1/admin/schedule/auto-scheduler")
def run_auto_scheduler():
    db = load_data()
    db["master_schedule"]["data"] = generate_enterprise_schedule(db)
    db["master_schedule"]["status"] = "DRAFT"
    db["audit_logs"].insert(0, {
        "id": f"AUD-{len(db['audit_logs'])+1}", "actor": "linhls (ADMIN)",
        "action": "AUTO_SCHEDULER_RUN", "target": "Master Schedule Generated V3.8",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reason": "Chạy thuật toán Auto-Scheduler chuẩn WFM"
    })
    save_data(db)
    return {"success": True, "message": "⚡ Đã chạy thuật toán Auto-Scheduler thành công!", "schedule": db["master_schedule"]}

@app.get("/api/v1/admin/compliance")
def get_compliance(): return load_data()["compliance"]

@app.get("/api/v1/admin/handbook")
def get_handbook(): return load_data()["handbook"]

@app.post("/api/v1/admin/handbook")
def create_handbook(data: HandbookNote):
    db = load_data()
    new_h = {"id": f"HB-0{len(db['handbook'])+1}", "title": data.title, "content": data.content, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    db["handbook"].insert(0, new_h)
    save_data(db)
    return {"success": True, "handbook": db["handbook"]}

@app.get("/api/v1/admin/audit-logs")
def get_audit_logs(): return load_data()["audit_logs"]

@app.get("/", response_class=HTMLResponse)
def home_dashboard():
    return r"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <title>CC TEAM - SMS | Enterprise Edition V3.8 (3-Tier RBAC)</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    </head>
    <body class="bg-gray-100 font-sans" x-data="enterpriseApp()" x-init="initApp()">

        <!-- MÀN HÌNH ĐĂNG NHẬP PHÂN QUYỀN ĐA TẦNG -->
        <div x-show="!isLoggedIn" class="fixed inset-0 bg-slate-900 flex items-center justify-center z-50 p-4">
            <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 space-y-6">
                <div class="text-center space-y-2">
                    <div class="w-14 h-14 bg-emerald-600 rounded-xl mx-auto flex items-center justify-center text-white font-extrabold text-xl shadow-lg">CC</div>
                    <h1 class="text-2xl font-black text-gray-900">CC TEAM - SMS</h1>
                    <p class="text-xs text-gray-500 uppercase tracking-wider">Cổng Đăng Nhập Vận Hành Tổng Đài</p>
                </div>
                
                <form @submit.prevent="handleLogin()" class="space-y-4">
                    <div>
                        <label class="block text-xs font-bold text-gray-700 uppercase mb-1">Tên đăng nhập (Username)</label>
                        <input type="text" x-model="loginForm.username" placeholder="VD: linhls, sup_nam, agent_a" class="w-full border rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-emerald-500 outline-none" required>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-gray-700 uppercase mb-1">Mật khẩu (Password)</label>
                        <input type="password" x-model="loginForm.password" placeholder="Mật khẩu..." class="w-full border rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-emerald-500 outline-none" required>
                    </div>
                    <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-xl shadow-lg transition duration-200 text-sm">
                        🔐 Đăng nhập Hệ thống
                    </button>
                </form>

                <div class="bg-gray-50 p-4 rounded-xl border text-xs space-y-1.5 text-gray-600">
                    <p class="font-bold text-gray-800">💡 Tài khoản kiểm thử nhanh:</p>
                    <p>• 👑 <b>Admin:</b> linhls / 123 (Toàn quyền 9 Menu)</p>
                    <p>• 🛡️ <b>Supervisor:</b> sup_nam / 123 (Điều phối 8 Menu)</p>
                    <p>• 👤 <b>User/Agent:</b> agent_a / 123 (Cá nhân 7 Menu)</p>
                </div>
            </div>
        </div>

        <!-- GIAO DIỆN CHÍNH SAU KHI ĐĂNG NHẬP -->
        <div x-show="isLoggedIn" class="flex h-screen" style="display: none;">
            
            <!-- SIDEBAR PHÂN TÁCH RIÊNG BIỆT CHO 3 TẦNG (ADMIN / SUP / USER) -->
            <div class="w-72 bg-slate-900 text-white flex flex-col justify-between p-4 shadow-lg overflow-y-auto shrink-0">
                <div class="space-y-6">
                    <div class="flex items-center space-x-3 px-2">
                        <div class="w-9 h-9 rounded-lg bg-emerald-500 flex items-center justify-center font-bold text-white">CC</div>
                        <div>
                            <h1 class="font-bold text-emerald-400 text-sm">CC TEAM - SMS</h1>
                            <span class="text-xs text-slate-400 uppercase tracking-wider" x-text="'Tầng: ' + currentUser.role"></span>
                        </div>
                    </div>
                    
                    <nav class="space-y-1.5 text-sm">
                        
                        <!-- ================= TẦNG 1: ADMIN (9 MENU) ================= -->
                        <template x-if="currentUser.role === 'ADMIN'">
                            <div class="space-y-1.5">
                                <a href="#" @click="currentTab = 'overview'" :class="currentTab === 'overview' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">1. 🏠 Tổng quan & Sổ tay vận hành</a>
                                <a href="#" @click="currentTab = 'users'" :class="currentTab === 'users' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">2. 👥 Quản lý Tài khoản & Phân quyền</a>
                                <a href="#" @click="currentTab = 'skills'" :class="currentTab === 'skills' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">3. 🎯 Hồ sơ Kỹ năng (Skill Matrix)</a>
                                <a href="#" @click="currentTab = 'demands'" :class="currentTab === 'demands' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">4. ⚡ Định biên & Ma trận Giờ V3.8</a>
                                <a href="#" @click="currentTab = 'compliance'" :class="currentTab === 'compliance' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">5. ⚖️ Luật an toàn ca kíp</a>
                                <a href="#" @click="currentTab = 'global'" :class="currentTab === 'global' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">6. 📅 Lịch trực tổng thể (Master Schedule)</a>
                                <a href="#" @click="currentTab = 'search'" :class="currentTab === 'search' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">7. 🔍 Trao cứu vĩ mô</a>
                                <a href="#" @click="currentTab = 'reports'" :class="currentTab === 'reports' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">8. 📊 Báo cáo Vận hành</a>
                                <a href="#" @click="currentTab = 'audit'" :class="currentTab === 'audit' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">9. 🛡️ Sức khỏe Hệ thống (Audit Trail)</a>
                            </div>
                        </template>

                        <!-- ================= TẦNG 2: SUPERVISOR (8 MENU) ================= -->
                        <template x-if="currentUser.role === 'SUPERVISOR'">
                            <div class="space-y-1.5">
                                <a href="#" @click="currentTab = 'sup_sos'" :class="currentTab === 'sup_sos' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">1. 🚨 Tổng quan & Cảnh báo SOS</a>
                                <a href="#" @click="currentTab = 'global'" :class="currentTab === 'global' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">2. 📅 Phân ca trực tuyến & Chợ đổi ca</a>
                                <a href="#" @click="currentTab = 'sup_requests'" :class="currentTab === 'sup_requests' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">3. 📝 Xử lý Đơn từ & Bàn giao ca</a>
                                <a href="#" @click="currentTab = 'reports'" :class="currentTab === 'reports' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">4. 💰 Quản lý Công & Thu nhập đội ngũ</a>
                                <a href="#" @click="currentTab = 'sup_qa'" :class="currentTab === 'sup_qa' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">5. 📋 Đánh giá QA & Nhật ký sự cố</a>
                                <a href="#" @click="currentTab = 'search'" :class="currentTab === 'search' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">6. 🔍 Trao cứu & Thống kê đội ngũ</a>
                                <a href="#" @click="currentTab = 'overview'" :class="currentTab === 'overview' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">7. 📊 Báo cáo Vận hành</a>
                                <a href="#" @click="currentTab = 'sup_notices'" :class="currentTab === 'sup_notices' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">8. 📢 Quản trị Thông báo & Kiểm duyệt</a>
                            </div>
                        </template>

                        <!-- ================= TẦNG 3: USER / AGENT (7 MENU) ================= -->
                        <template x-if="currentUser.role === 'USER'">
                            <div class="space-y-1.5">
                                <a href="#" @click="currentTab = 'global'" :class="currentTab === 'global' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">1. 📅 Lịch trực & Đăng ký ca</a>
                                <a href="#" @click="currentTab = 'user_swap'" :class="currentTab === 'user_swap' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">2. 🔄 Chợ đổi ca chéo (Swap Board)</a>
                                <a href="#" @click="currentTab = 'user_salary'" :class="currentTab === 'user_salary' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">3. 💰 Ngày công & Thu nhập dự kiến</a>
                                <a href="#" @click="currentTab = 'user_requests'" :class="currentTab === 'user_requests' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">4. 📝 Gửi đơn từ / Yêu cầu</a>
                                <a href="#" @click="currentTab = 'overview'" :class="currentTab === 'overview' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">5. 📢 Thông báo chung</a>
                                <a href="#" @click="currentTab = 'user_forum'" :class="currentTab === 'user_forum' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">6. 💡 Trao đổi kinh nghiệm nghiệp vụ</a>
                                <a href="#" @click="currentTab = 'user_shiftlog'" :class="currentTab === 'user_shiftlog' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'" class="block py-2 px-3 rounded-lg font-medium">7. 📋 Nhật ký ca trực cá nhân</a>
                            </div>
                        </template>

                    </nav>
                </div>
                <div class="border-t border-slate-800 pt-3 space-y-2 text-center">
                    <div class="text-xs text-slate-300" x-text="currentUser.full_name + ' (' + currentUser.role + ')'"></div>
                    <button @click="logout()" class="w-full bg-red-600/80 hover:bg-red-600 text-white text-xs font-bold py-1.5 rounded-lg transition">🚪 Đăng xuất</button>
                </div>
            </div>

            <!-- MAIN CONTENT AREA -->
            <div class="flex-1 flex flex-col overflow-hidden">
                <header class="bg-white shadow px-6 py-4 flex justify-between items-center">
                    <h2 class="text-lg font-bold text-gray-800" x-text="getTabTitle()"></h2>
                    <div class="flex items-center space-x-3 bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-full">
                        <div class="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-sm" x-text="currentUser.full_name ? currentUser.full_name.charAt(0) : 'U'"></div>
                        <span class="text-sm font-medium text-gray-700" x-text="currentUser.full_name + ' (' + currentUser.role + ')'"></span>
                    </div>
                </header>

                <main class="flex-1 overflow-x-hidden overflow-y-auto bg-gray-50 p-6 space-y-6">
                    
                    <!-- MENU 1: TỔNG QUAN & SỔ TAY -->
                    <div x-show="currentTab === 'overview'" class="space-y-6">
                        <div class="grid grid-cols-4 gap-6">
                            <div class="bg-white p-5 rounded-xl shadow border-l-4 border-blue-500 space-y-1">
                                <p class="text-xs text-gray-500 font-semibold uppercase">Tổng nhân sự Active</p>
                                <p class="text-3xl font-extrabold text-gray-800" x-text="usersList.filter(u => u.status !== 'INACTIVE').length"></p>
                            </div>
                            <div class="bg-white p-5 rounded-xl shadow border-l-4 border-emerald-500 space-y-1">
                                <p class="text-xs text-gray-500 font-semibold uppercase">Trạng thái Lịch trực</p>
                                <p class="text-xl font-extrabold text-emerald-600" x-text="scheduleObj.status"></p>
                            </div>
                            <div class="bg-white p-5 rounded-xl shadow border-l-4 border-amber-500 space-y-1">
                                <p class="text-xs text-gray-500 font-semibold uppercase">Hồ sơ kỹ năng</p>
                                <p class="text-3xl font-extrabold text-amber-600" x-text="skillsList.length"></p>
                            </div>
                            <div class="bg-white p-5 rounded-xl shadow border-l-4 border-purple-500 space-y-1">
                                <p class="text-xs text-gray-500 font-semibold uppercase">Hộp đen Audit Logs</p>
                                <p class="text-3xl font-extrabold text-purple-600" x-text="auditLogsList.length"></p>
                            </div>
                        </div>
                        <div class="bg-white p-6 rounded-xl shadow space-y-4">
                            <h3 class="text-base font-bold text-gray-800">📒 Sổ tay & Thông báo chính thống từ Ban Lãnh đạo</h3>
                            <template x-for="hb in handbookList" :key="hb.id">
                                <div class="p-4 rounded-xl border bg-gray-50 space-y-1">
                                    <h4 class="font-bold text-sm text-gray-800" x-text="hb.title"></h4>
                                    <p class="text-sm text-gray-600" x-text="hb.content"></p>
                                    <div class="text-[10px] text-gray-400" x-text="'Cập nhật: ' + hb.updated_at"></div>
                                </div>
                            </template>
                        </div>
                    </div>

                    <!-- ADMIN MENU 2: USERS -->
                    <div x-show="currentTab === 'users'" class="bg-white p-6 rounded-xl shadow space-y-6" style="display: none;">
                        <div class="flex flex-wrap justify-between items-center gap-4">
                            <div>
                                <h3 class="text-base font-bold text-gray-800">👥 Danh mục Tài khoản & Phân quyền Hệ thống</h3>
                                <p class="text-xs text-gray-500 mt-0.5">Thêm/Sửa/Khóa nhân sự. Tài khoản ADMIN miễn trừ khỏi kỹ năng & lịch trực.</p>
                            </div>
                            <div class="flex flex-wrap items-center gap-2">
                                <button @click="showInactiveModal = true" class="bg-amber-50 border border-amber-300 text-amber-800 px-3 py-2 rounded-lg text-xs font-bold hover:bg-amber-100 shadow">
                                    👥 Nhân sự đã khóa (<span x-text="usersList.filter(u => u.status === 'INACTIVE').length"></span>)
                                </button>
                                <a href="/api/v1/admin/users/template-csv" class="bg-gray-100 border text-gray-700 px-3 py-2 rounded-lg text-xs font-semibold hover:bg-gray-200">📥 Mẫu CSV</a>
                                <button @click="$refs.csvInput.click()" class="bg-blue-50 border border-blue-200 text-blue-700 px-3 py-2 rounded-lg text-xs font-semibold hover:bg-blue-100">📤 Import</button>
                                <input type="file" x-ref="csvInput" @change="uploadCsv($event)" accept=".csv" class="hidden">
                                <a href="/api/v1/admin/export-csv" class="bg-purple-50 border border-purple-200 text-purple-700 px-3 py-2 rounded-lg text-xs font-semibold hover:bg-purple-100">💾 Export</a>
                                <button @click="openCreateModal()" class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-emerald-700 shadow">+ Thêm nhân sự</button>
                            </div>
                        </div>

                        <div class="border rounded-xl overflow-hidden shadow-sm">
                            <table class="min-w-full divide-y divide-gray-200">
                                <thead class="bg-gray-50">
                                    <tr>
                                        <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Mã NV</th>
                                        <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Họ và tên</th>
                                        <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Vai trò</th>
                                        <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Team</th>
                                        <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Trạng thái</th>
                                        <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Thao tác</th>
                                    </tr>
                                </thead>
                                <tbody class="bg-white divide-y divide-gray-200">
                                    <template x-for="u in usersList.filter(u => u.status !== 'INACTIVE')" :key="u.id">
                                        <tr>
                                            <td class="px-4 py-3 text-sm font-bold text-blue-600" x-text="u.id"></td>
                                            <td class="px-4 py-3 text-sm font-semibold text-gray-900" x-text="u.full_name"></td>
                                            <td class="px-4 py-3 text-sm"><span class="px-2.5 py-1 rounded text-xs font-bold bg-purple-50 text-purple-700" x-text="u.role"></span></td>
                                            <td class="px-4 py-3 text-sm text-gray-600 text-xs font-medium" x-text="u.team"></td>
                                            <td class="px-4 py-3 text-sm"><span class="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800" x-text="u.status"></span></td>
                                            <td class="px-4 py-3 text-right text-sm space-x-2">
                                                <button @click="editUser(u)" class="text-blue-600 bg-blue-50 px-2.5 py-1 rounded font-semibold text-xs">Sửa</button>
                                                <button @click="deleteUser(u.id)" class="text-red-600 bg-red-50 px-2.5 py-1 rounded font-semibold text-xs">Khóa</button>
                                            </td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- ADMIN MENU 3: SKILL MATRIX -->
                    <div x-show="currentTab === 'skills'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">🎯 Hồ sơ Kỹ năng Nhân sự (Skill Matrix)</h3>
                        <table class="min-w-full divide-y divide-gray-200">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Mã NV</th>
                                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Họ và tên</th>
                                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Cấp độ</th>
                                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Kỹ năng</th>
                                    <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Thao tác</th>
                                </tr>
                            </thead>
                            <tbody class="bg-white divide-y divide-gray-200">
                                <template x-for="sk in skillsList" :key="sk.id">
                                    <tr>
                                        <td class="px-4 py-3 text-sm font-bold text-gray-700" x-text="sk.employee_id"></td>
                                        <td class="px-4 py-3 text-sm font-bold text-gray-900" x-text="sk.employee"></td>
                                        <td class="px-4 py-3 text-sm"><span class="px-2.5 py-1 rounded text-xs font-bold bg-blue-50 text-blue-700" x-text="sk.level"></span></td>
                                        <td class="px-4 py-3 text-sm space-x-1">
                                            <template x-for="s in sk.skills"><span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 text-xs font-bold border" x-text="s"></span></template>
                                        </td>
                                        <td class="px-4 py-3 text-right text-sm">
                                            <button @click="openEditSkill(sk)" class="text-blue-600 bg-blue-50 px-2.5 py-1 rounded font-semibold text-xs">Cập nhật</button>
                                        </td>
                                    </tr>
                                </template>
                            </tbody>
                        </table>
                    </div>

                    <!-- ADMIN MENU 4: DEMANDS -->
                    <div x-show="currentTab === 'demands'" class="bg-white p-6 rounded-xl shadow space-y-6" style="display: none;">
                        <div class="flex justify-between items-center border-b pb-4">
                            <h3 class="text-base font-bold text-gray-800">⚡ Định biên & Ma trận Giờ V3.8 (Min & Target)</h3>
                            <div class="flex items-center space-x-2">
                                <select x-model="selectedDay" class="border rounded-lg px-3 py-2 text-sm font-bold bg-slate-50 text-slate-800">
                                    <template x-for="d in matrixDays" :key="d.key"><option :value="d.key" x-text="d.name"></option></template>
                                </select>
                                <button @click="copyTemplate()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg text-xs font-semibold shadow">📥 Sao chép mẫu tuần</button>
                            </div>
                        </div>
                        <div class="overflow-x-auto border rounded-xl shadow-sm">
                            <table class="min-w-full divide-y divide-gray-200 text-center text-sm">
                                <thead class="bg-slate-900 text-white">
                                    <tr>
                                        <th class="px-4 py-3 text-left font-semibold text-xs uppercase sticky left-0 bg-slate-900 z-10">Kênh trực</th>
                                        <template x-for="h in matrixHours" :key="h"><th class="px-2 py-3 font-bold text-xs" x-text="h + 'h'"></th></template>
                                    </tr>
                                </thead>
                                <tbody class="bg-white divide-y divide-gray-200">
                                    <template x-for="chan in matrixChannels" :key="chan">
                                        <tr>
                                            <td class="px-4 py-2.5 text-left font-bold text-gray-800 sticky left-0 bg-white z-10" x-text="chan"></td>
                                            <template x-for="h in matrixHours" :key="h">
                                                <td class="px-1 py-2">
                                                    <div class="flex flex-col space-y-1 p-1 rounded border bg-gray-50/50">
                                                        <div class="flex items-center space-x-1 justify-between bg-red-50 px-1 py-0.5 rounded border border-red-200">
                                                            <span class="text-[9px] font-bold text-red-600">Min</span>
                                                            <input type="number" min="0" :value="getCellVal(selectedDay, chan, h, 'min')" @change="updateCell(selectedDay, chan, h, 'min', $event.target.value)" class="w-7 text-center border rounded text-xs font-bold text-red-700 bg-white">
                                                        </div>
                                                        <div class="flex items-center space-x-1 justify-between bg-blue-50 px-1 py-0.5 rounded border border-blue-200">
                                                            <span class="text-[9px] font-bold text-blue-600">Tgt</span>
                                                            <input type="number" min="0" :value="getCellVal(selectedDay, chan, h, 'target')" @change="updateCell(selectedDay, chan, h, 'target', $event.target.value)" class="w-7 text-center border rounded text-xs font-bold text-blue-700 bg-white">
                                                        </div>
                                                    </div>
                                                </td>
                                            </template>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- ADMIN MENU 5: COMPLIANCE -->
                    <div x-show="currentTab === 'compliance'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">⚖️ Luật an toàn ca kíp & Phân quyền (WFM Rules)</h3>
                        <table class="min-w-full divide-y divide-gray-200 text-sm">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-4 py-2 text-left">Mã luật</th>
                                    <th class="px-4 py-2 text-left">Quy định</th>
                                    <th class="px-4 py-2 text-left">Ngưỡng</th>
                                    <th class="px-4 py-2 text-left">Hành động</th>
                                </tr>
                            </thead>
                            <tbody>
                                <template x-for="r in complianceList" :key="r.rule_id">
                                    <tr>
                                        <td class="px-4 py-2 font-bold" x-text="r.rule_id"></td>
                                        <td class="px-4 py-2" x-text="r.name"></td>
                                        <td class="px-4 py-2 font-bold text-emerald-600" x-text="r.limit_value"></td>
                                        <td class="px-4 py-2"><span class="px-2 py-1 bg-purple-50 text-purple-700 rounded text-xs font-bold" x-text="r.action"></span></td>
                                    </tr>
                                </template>
                            </tbody>
                        </table>
                    </div>

                    <!-- MENU 6: MASTER SCHEDULE (DÙNG CHUNG CHO CẢ 3 TẦNG VỚI QUYỀN HẠN KHÁC NHAU) -->
                    <div x-show="currentTab === 'global'" class="bg-white p-6 rounded-xl shadow space-y-6" style="display: none;">
                        <div class="flex flex-wrap justify-between items-center gap-4 border-b pb-4">
                            <div>
                                <h3 class="text-base font-bold text-gray-800" x-text="currentUser.role === 'USER' ? '📅 Lịch trực & Đăng ký ca cá nhân' : '📅 Lịch trực tổng thể (Master Schedule)'"></h3>
                                <p class="text-xs text-gray-500 mt-0.5" x-text="scheduleObj.week_title"></p>
                            </div>
                            <div class="flex flex-wrap items-center gap-3">
                                <div class="flex items-center space-x-2 bg-gray-100 px-3 py-1.5 rounded-lg border" x-show="currentUser.role !== 'USER'">
                                    <span class="text-xs font-semibold text-gray-500">Trạng thái:</span>
                                    <select x-model="scheduleObj.status" @change="changeScheduleStatus($event.target.value)" class="text-xs font-extrabold px-2 py-1 rounded border bg-white shadow-sm" :class="getStatusColor(scheduleObj.status)">
                                        <option value="DRAFT">DRAFT</option>
                                        <option value="CHECKED">CHECKED</option>
                                        <option value="PUBLISHED">PUBLISHED</option>
                                        <option value="LOCKED">LOCKED (Chỉ Admin sửa)</option>
                                    </select>
                                </div>
                                <button x-show="currentUser.role !== 'USER'" @click="runAutoScheduler()" class="bg-purple-600 hover:bg-purple-700 text-white px-3 py-2 rounded-lg text-xs font-semibold shadow">⚡ Auto-Scheduler</button>
                                <select x-model="schedDay" class="border rounded-lg px-3 py-2 text-sm font-bold bg-slate-50 text-slate-800">
                                    <template x-for="d in matrixDays" :key="d.key"><option :value="d.key" x-text="d.name"></option></template>
                                </select>
                            </div>
                        </div>

                        <!-- GÓC NHÌN LỊCH -->
                        <div class="space-y-4">
                            <div class="overflow-x-auto border rounded-xl shadow-sm">
                                <table class="min-w-full divide-y divide-gray-200 text-center text-xs">
                                    <thead class="bg-slate-900 text-white">
                                        <tr>
                                            <th class="px-4 py-3 text-left font-semibold uppercase sticky left-0 bg-slate-900 z-10">Nhân sự (<span x-text="schedDay"></span>)</th>
                                            <template x-for="h in matrixHours" :key="h"><th class="px-2 py-3 font-bold" x-text="h + 'h'"></th></template>
                                        </tr>
                                    </thead>
                                    <tbody class="bg-white divide-y divide-gray-200">
                                        <template x-for="u in filteredStaffList" :key="u.id">
                                            <tr class="hover:bg-gray-50">
                                                <td class="px-4 py-2.5 text-left font-bold text-gray-800 sticky left-0 bg-white z-10">
                                                    <div x-text="u.full_name"></div>
                                                    <div class="text-[10px] text-gray-400 font-normal" x-text="u.id + ' • ' + u.role + ' • ' + u.team"></div>
                                                </td>
                                                <template x-for="h in matrixHours" :key="h">
                                                    <td class="px-1 py-2">
                                                        <span x-show="u.role === 'ADMIN'" class="px-2 py-1 bg-purple-50 text-purple-700 font-bold rounded text-[10px] border border-purple-200">OVERLORD</span>
                                                        
                                                        <!-- Nếu là USER: chỉ xem hoặc đăng ký ca của chính mình -->
                                                        <span x-show="currentUser.role === 'USER' && currentUser.id !== u.id" class="px-2 py-1 rounded text-[10px] font-bold" :class="getDutyColor(getSchedCell(schedDay, u.id, h))" x-text="getSchedCell(schedDay, u.id, h)"></span>
                                                        
                                                        <select x-show="u.role !== 'ADMIN' && (currentUser.role !== 'USER' || currentUser.id === u.id)" :disabled="currentUser.role === 'USER' && scheduleObj.status === 'LOCKED'" :value="getSchedCell(schedDay, u.id, h)" @change="updateSchedCell(schedDay, u.id, h, $event.target.value)" class="border rounded p-1 text-[11px] font-bold outline-none" :class="getDutyColor(getSchedCell(schedDay, u.id, h))">
                                                            <option value="OFF">OFF</option>
                                                            <option value="BREAK">☕ BREAK</option>
                                                            <template x-for="chan in matrixChannels"><option :value="chan" x-text="chan"></option></template>
                                                        </select>
                                                    </td>
                                                </template>
                                            </tr>
                                        </template>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <!-- ADMIN MENU 7 & SUP MENU 6: TRAO CỨU VĨ MÔ -->
                    <div x-show="currentTab === 'search'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">🔍 Trao cứu & Thống kê vĩ mô</h3>
                        <div class="flex space-x-3"><input type="text" placeholder="Nhập từ khóa tìm kiếm nhân sự, ca trực..." class="border rounded-lg p-2 text-sm flex-1"><button class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm">Tra cứu</button></div>
                    </div>

                    <!-- ADMIN MENU 8 & SUP MENU 4: BÁO CÁO & QUẢN LÝ LƯƠNG -->
                    <div x-show="currentTab === 'reports'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📊 Báo cáo Vận hành & Quỹ lương dự kiến</h3>
                        <div class="grid grid-cols-2 gap-4">
                            <div class="p-4 border rounded-xl bg-gray-50">Tổng giờ làm việc: <b>4,850 giờ</b></div>
                            <div class="p-4 border rounded-xl bg-gray-50">Quỹ lương ước tính: <b class="text-emerald-600">348,500,000 đ</b></div>
                        </div>
                    </div>

                    <!-- ADMIN MENU 9: AUDIT TRAIL -->
                    <div x-show="currentTab === 'audit'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">🛡️ Sức khỏe Hệ thống (Audit Trail - Hộp đen trung tâm)</h3>
                        <div class="border rounded-xl overflow-hidden max-h-[500px] overflow-y-auto">
                            <table class="min-w-full divide-y divide-gray-200 text-xs">
                                <thead class="bg-gray-50 sticky top-0">
                                    <tr>
                                        <th class="px-4 py-3 text-left font-semibold text-gray-500 uppercase">Mã Log</th>
                                        <th class="px-4 py-3 text-left font-semibold text-gray-500 uppercase">Tài khoản</th>
                                        <th class="px-4 py-3 text-left font-semibold text-gray-500 uppercase">Hành động</th>
                                        <th class="px-4 py-3 text-left font-semibold text-gray-500 uppercase">Mục tiêu / Lý do</th>
                                        <th class="px-4 py-3 text-left font-semibold text-gray-500 uppercase">Thời gian</th>
                                    </tr>
                                </thead>
                                <tbody class="bg-white divide-y divide-gray-200">
                                    <template x-for="log in auditLogsList" :key="log.id">
                                        <tr>
                                            <td class="px-4 py-3 font-bold text-gray-700" x-text="log.id"></td>
                                            <td class="px-4 py-3 text-blue-600 font-semibold" x-text="log.actor"></td>
                                            <td class="px-4 py-3 font-bold text-slate-800" x-text="log.action"></td>
                                            <td class="px-4 py-3 text-gray-600" x-text="log.target + ' (' + log.reason + ')'"></td>
                                            <td class="px-4 py-3 text-gray-500" x-text="log.timestamp"></td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- ================= SUP & USER CHUYÊN BIỆT CÁC MENU KHÁC ================= -->
                    <div x-show="currentTab === 'sup_sos'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-red-600">🚨 Tổng quan & Cảnh báo SOS Real-time</h3>
                        <div class="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-800 font-semibold">
                            ⚠️ Khung giờ hiện tại (10:00h): Thiếu hụt 2 nhân sự kênh Call (VNP). Danh sách nhân sự đang OFF có thể gọi điện thay thế: <b>Nguyễn Văn A, Trần Thị B</b>.
                        </div>
                    </div>

                    <div x-show="currentTab === 'sup_requests'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📝 Xử lý Đơn từ & Bàn giao ca (Shift Handover)</h3>
                        <p class="text-xs text-gray-500">Danh sách đơn xin nghỉ phép, đổi ca của nhân viên chờ duyệt 1 chạm.</p>
                        <div class="border rounded-xl p-4 bg-gray-50 space-y-2">
                            <div class="flex justify-between items-center text-sm font-semibold">
                                <span>NV: Nguyễn Văn A - Xin đổi ca ngày Thứ Ba sang ca chiều</span>
                                <div class="space-x-2">
                                    <button class="bg-emerald-600 text-white px-3 py-1 rounded text-xs">Duyệt</button>
                                    <button class="bg-red-600 text-white px-3 py-1 rounded text-xs">Từ chối</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div x-show="currentTab === 'sup_qa'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📋 Đánh giá QA & Nhật ký sự cố (Incident Log)</h3>
                        <p class="text-xs text-gray-500">Chấm điểm nhanh QA và ghi nhận thưởng/phạt KPI cá nhân.</p>
                    </div>

                    <div x-show="currentTab === 'sup_notices'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📢 Quản trị Thông báo & Kiểm duyệt Nghiệp vụ</h3>
                        <p class="text-xs text-gray-500">Đăng tin thông báo chung và kiểm duyệt bài viết kinh nghiệm của Agent.</p>
                    </div>

                    <!-- USER MENU CHUYÊN BIỆT -->
                    <div x-show="currentTab === 'user_swap'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">🔄 Chợ đổi ca chéo (Swap Board)</h3>
                        <p class="text-xs text-gray-500">Đăng tin công khai khi cần đổi ca với đồng nghiệp, chờ Sup duyệt.</p>
                        <button class="bg-blue-600 text-white px-4 py-2 rounded-lg text-xs font-bold">+ Đăng tin đổi ca</button>
                    </div>

                    <div x-show="currentTab === 'user_salary'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">💰 Ngày công & Thu nhập dự kiến cá nhân</h3>
                        <div class="p-4 border rounded-xl bg-emerald-50 text-emerald-900 space-y-1">
                            <p class="text-xs font-bold uppercase">Ước tính tháng này:</p>
                            <p class="text-2xl font-extrabold">22 Ca trực • 176 Giờ • 14,200,000 đ</p>
                        </div>
                    </div>

                    <div x-show="currentTab === 'user_requests'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📝 Gửi đơn từ / Yêu cầu cá nhân</h3>
                        <button class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-xs font-bold">+ Gửi đơn xin nghỉ / Đổi ca</button>
                    </div>

                    <div x-show="currentTab === 'user_forum'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">💡 Trao đổi kinh nghiệm nghiệp vụ</h3>
                        <p class="text-xs text-gray-500">Diễn đàn nội bộ chia sẻ mẹo xử lý tình huống khó với đồng nghiệp.</p>
                    </div>

                    <div x-show="currentTab === 'user_shiftlog'" class="bg-white p-6 rounded-xl shadow space-y-4" style="display: none;">
                        <h3 class="text-base font-bold text-gray-800">📋 Nhật ký ca trực cá nhân (Shift Log)</h3>
                        <textarea placeholder="Ghi chú ngắn cuối ca về công việc hoặc sự cố kỹ thuật..." class="w-full border rounded-lg p-3 text-sm" rows="4"></textarea>
                        <button class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-xs font-bold">Lưu nhật ký ca</button>
                    </div>

                </main>
            </div>

            <!-- MODAL INACTIVE USERS -->
            <div x-show="showInactiveModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" style="display: none;">
                <div class="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 space-y-4">
                    <h3 class="text-lg font-bold text-gray-800">📋 Danh sách Nhân sự đã khóa</h3>
                    <table class="min-w-full divide-y divide-gray-200 text-sm">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-4 py-2 text-left">Mã NV</th>
                                <th class="px-4 py-2 text-left">Họ tên</th>
                                <th class="px-4 py-2 text-right">Thao tác</th>
                            </tr>
                        </thead>
                        <tbody>
                            <template x-for="u in usersList.filter(u => u.status === 'INACTIVE')" :key="u.id">
                                <tr>
                                    <td class="px-4 py-2 font-bold" x-text="u.id"></td>
                                    <td class="px-4 py-2" x-text="u.full_name"></td>
                                    <td class="px-4 py-2 text-right"><button @click="restoreUser(u.id)" class="bg-emerald-600 text-white px-2.5 py-1 rounded text-xs font-bold">Khôi phục</button></td>
                                </tr>
                            </template>
                        </tbody>
                    </table>
                    <div class="flex justify-end"><button @click="showInactiveModal = false" class="px-4 py-2 bg-gray-100 rounded text-sm font-semibold">Đóng</button></div>
                </div>
            </div>

            <!-- MODAL THÊM/SỬA USER -->
            <div x-show="showUserModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" style="display: none;">
                <div class="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                    <h3 class="text-lg font-bold text-gray-800" x-text="isEditMode ? 'Chỉnh sửa nhân sự' : 'Thêm nhân sự mới'"></h3>
                    <div class="space-y-3">
                        <div><label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Mã nhân sự</label><input type="text" x-model="userForm.id" :disabled="isEditMode" class="w-full border rounded-lg px-3 py-2 text-sm disabled:bg-gray-100 font-bold"></div>
                        <div><label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Họ và tên</label><input type="text" x-model="userForm.full_name" class="w-full border rounded-lg px-3 py-2 text-sm"></div>
                        <div><label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Mật khẩu</label><input type="password" x-model="userForm.password" class="w-full border rounded-lg px-3 py-2 text-sm"></div>
                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Vai trò</label>
                                <select x-model="userForm.role" class="w-full border rounded-lg px-3 py-2 text-sm font-bold text-blue-600">
                                    <option value="USER">USER</option>
                                    <option value="SUPERVISOR">SUPERVISOR</option>
                                    <option value="ADMIN">ADMIN</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Trạng thái</label>
                                <select x-model="userForm.status" class="w-full border rounded-lg px-3 py-2 text-sm font-bold text-emerald-600">
                                    <option value="ACTIVE">ACTIVE</option>
                                    <option value="ON_LEAVE">ON_LEAVE</option>
                                </select>
                            </div>
                        </div>
                        <div><label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Team</label><input type="text" x-model="userForm.team" class="w-full border rounded-lg px-3 py-2 text-sm"></div>
                    </div>
                    <div class="flex justify-end space-x-3 pt-2">
                        <button @click="showUserModal = false" class="px-4 py-2 bg-gray-100 rounded-lg text-sm font-semibold">Hủy</button>
                        <button @click="saveUser()" class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold">Lưu lại</button>
                    </div>
                </div>
            </div>

            <!-- MODAL SỬA SKILL -->
            <div x-show="showSkillModal || showSkillModalFlag" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" style="display: none;">
                <div class="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                    <h3 class="text-lg font-bold text-gray-800">Cập nhật Kỹ năng: <span class="text-blue-600" x-text="skillForm.employee"></span></h3>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Cấp độ (Level)</label>
                            <select x-model="skillForm.level" class="w-full border rounded-lg px-3 py-2 text-sm">
                                <option value="Junior">Junior</option>
                                <option value="Senior">Senior</option>
                                <option value="Expert">Expert</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Kỹ năng</label>
                            <div class="grid grid-cols-2 gap-2 text-sm">
                                <label><input type="checkbox" value="CALL" x-model="skillForm.skills"> CALL</label>
                                <label><input type="checkbox" value="CHAT" x-model="skillForm.skills"> CHAT</label>
                                <label><input type="checkbox" value="KHL" x-model="skillForm.skills"> KHL</label>
                                <label><input type="checkbox" value="VIP" x-model="skillForm.skills"> VIP</label>
                                <label><input type="checkbox" value="Ngoại ngữ" x-model="skillForm.skills"> Ngoại ngữ</label>
                            </div>
                        </div>
                    </div>
                    <div class="flex justify-end space-x-3 pt-2">
                        <button @click="showSkillModal = false; showSkillModalFlag = false;" class="px-4 py-2 bg-gray-100 rounded-lg text-sm font-semibold">Hủy</button>
                        <button @click="saveSkill()" class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold">Lưu</button>
                    </div>
                </div>
            </div>

            <!-- MODAL REASON -->
            <div x-show="showReasonModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" style="display: none;">
                <div class="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
                    <h3 class="text-lg font-bold text-gray-800" x-text="scheduleObj.status === 'LOCKED' ? '🚨 Xử lý ngoại lệ sự cố (Trạng thái LOCKED)' : '📝 Yêu cầu nhập lý do điều chỉnh lịch'"></h3>
                    <p class="text-xs text-gray-500">Bắt buộc nhập lý do để lưu vào Audit Trail.</p>
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 uppercase mb-1">Lý do thay đổi <span class="text-red-500">*</span>:</label>
                        <textarea x-model="editReason" rows="3" placeholder="VD: NV A ốm đột xuất, NV B thay thế ca..." class="w-full border rounded-lg p-2 text-sm"></textarea>
                    </div>
                    <div class="flex justify-end space-x-3 pt-2">
                        <button @click="showReasonModal = false" class="px-4 py-2 bg-gray-100 rounded-lg text-sm font-semibold">Hủy</button>
                        <button @click="confirmUpdateSchedCell()" class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold">Xác nhận</button>
                    </div>
                </div>
            </div>

        </div>

        <script>
            function enterpriseApp() {
                return {
                    isLoggedIn: false,
                    loginForm: { username: '', password: '' },
                    currentUser: { id: '', full_name: '', role: 'USER' },

                    currentTab: 'overview',
                    usersList: [], skillsList: [], complianceList: [], handbookList: [], auditLogsList: [],
                    matrixChannels: [], matrixDays: [], matrixHours: [], matrixData: {},
                    scheduleObj: { status: 'PUBLISHED', week_title: '', data: {} },
                    selectedDay: 'Mon', schedDay: 'Mon',
                    schedSearchQuery: '', schedTeamFilter: 'ALL',
                    
                    userForm: { id: '', full_name: '', password: '123', role: 'USER', status: 'ACTIVE', team: 'Team CSKH 1' },
                    skillForm: { id: '', employee: '', level: 'Junior', skills: [] },
                    showSkillModalFlag: false, showInactiveModal: false, showUserModal: false, showSkillModal: false, showReasonModal: false, isEditMode: false,
                    pendingEdit: null, editReason: '',

                    async initApp() {
                        let savedUser = localStorage.getItem('cc_current_user');
                        if (savedUser) {
                            this.currentUser = JSON.parse(savedUser);
                            this.isLoggedIn = true;
                            await this.loadAllData();
                        }
                    },
                    async handleLogin() {
                        try {
                            let res = await fetch('/api/v1/auth/login', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(this.loginForm)
                            });
                            let result = await res.json();
                            if (res.ok && result.success) {
                                this.currentUser = result.user;
                                localStorage.setItem('cc_current_user', JSON.stringify(this.currentUser));
                                this.isLoggedIn = true;
                                await this.loadAllData();
                            } else {
                                alert(result.detail || "Đăng nhập thất bại!");
                            }
                        } catch(e) {
                            alert("Lỗi kết nối đến máy chủ!");
                        }
                    },
                    logout() {
                        localStorage.removeItem('cc_current_user');
                        this.isLoggedIn = false;
                        this.loginForm = { username: '', password: '' };
                    },
                    async loadAllData() {
                        let resU = await fetch('/api/v1/admin/users'); this.usersList = await resU.json();
                        let resS = await fetch('/api/v1/admin/skills'); this.skillsList = await resS.json();
                        let resC = await fetch('/api/v1/admin/compliance'); this.complianceList = await resC.json();
                        let resH = await fetch('/api/v1/admin/handbook'); this.handbookList = await resH.json();
                        let resA = await fetch('/api/v1/admin/audit-logs'); this.auditLogsList = await resA.json();
                        let resM = await fetch('/api/v1/admin/matrix-v3'); let mJson = await resM.json();
                        this.matrixChannels = mJson.channels; this.matrixDays = mJson.days; this.matrixHours = mJson.hours; this.matrixData = mJson.matrix;
                        let resSch = await fetch('/api/v1/admin/schedule'); this.scheduleObj = await resSch.json();
                        
                        // Định hướng tab mặc định theo Role
                        if (this.currentUser.role === 'USER') {
                            this.currentTab = 'global';
                        } else if (this.currentUser.role === 'SUPERVISOR') {
                            this.currentTab = 'sup_sos';
                        } else {
                            this.currentTab = 'overview';
                        }
                    },
                    getTabTitle() {
                        const titles = {
                            'overview': '1. Tổng quan & Sổ tay vận hành', 'users': '2. Quản lý Tài khoản & Phân quyền',
                            'skills': '3. Hồ sơ Kỹ năng (Skill Matrix)', 'demands': '4. Định biên & Ma trận Giờ',
                            'compliance': '5. Luật an toàn ca kíp', 'global': '6. Lịch trực tổng thể / Cá nhân',
                            'search': '7. Trao cứu vĩ mô', 'reports': '8. Báo cáo & Tài chính', 'audit': '9. Sức khỏe Hệ thống (Audit Trail)',
                            'sup_sos': '1. Tổng quan & Cảnh báo SOS', 'sup_requests': '3. Xử lý Đơn từ & Bàn giao ca',
                            'sup_qa': '5. Đánh giá QA & Nhật ký sự cố', 'sup_notices': '8. Quản trị Thông báo & Kiểm duyệt',
                            'user_swap': '2. Chợ đổi ca chéo (Swap Board)', 'user_salary': '3. Ngày công & Thu nhập dự kiến',
                            'user_requests': '4. Gửi đơn từ / Yêu cầu', 'user_forum': '6. Trao đổi kinh nghiệm nghiệp vụ', 'user_shiftlog': '7. Nhật ký ca trực cá nhân'
                        };
                        return titles[this.currentTab] || 'Hệ thống Quản lý';
                    },
                    getCellVal(day, chan, hour, type) {
                        try { return this.matrixData[day][chan][hour][type]; } catch (e) { return type === 'min' ? 2 : 4; }
                    },
                    async updateCell(day, chan, hour, type, val) {
                        if (this.currentUser.role === 'USER') return;
                        let currentMin = this.getCellVal(day, chan, hour, 'min');
                        let currentTgt = this.getCellVal(day, chan, hour, 'target');
                        let numVal = parseInt(val) || 0;
                        let newMin = type === 'min' ? numVal : currentMin;
                        let newTgt = type === 'target' ? numVal : currentTgt;
                        if (newTgt < newMin) newTgt = newMin;

                        let res = await (await fetch('/api/v1/admin/matrix-v3/update-cell', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ day: day, channel: chan, hour: hour, min_val: newMin, target_val: newTgt })
                        })).json();
                        if (res.success) { this.matrixData = res.matrix; }
                    },
                    async copyTemplate() {
                        if (this.currentUser.role === 'USER') return;
                        if (!confirm('Sao chép định mức của ngày ' + this.selectedDay + ' sang cả tuần?')) return;
                        let res = await (await fetch('/api/v1/admin/matrix-v3/copy-template', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ source_day: this.selectedDay })
                        })).json();
                        if (res.success) { this.matrixData = res.matrix; alert(res.message); }
                    },
                    get filteredStaffList() {
                        let list = this.usersList.filter(u => u.status === 'ACTIVE');
                        if (this.currentUser.role === 'USER') {
                            list = list.filter(u => u.id === this.currentUser.id);
                        } else {
                            if (this.schedTeamFilter !== 'ALL') list = list.filter(u => u.team === this.schedTeamFilter);
                            if (this.schedSearchQuery.trim()) {
                                let q = this.schedSearchQuery.toLowerCase();
                                list = list.filter(u => u.full_name.toLowerCase().includes(q) || u.id.toLowerCase().includes(q));
                            }
                        }
                        return list;
                    },
                    getStatusColor(status) {
                        if (status === 'DRAFT') return 'bg-gray-100 text-gray-800';
                        if (status === 'CHECKED') return 'bg-blue-100 text-blue-800';
                        if (status === 'PUBLISHED') return 'bg-emerald-100 text-emerald-800';
                        return 'bg-purple-100 text-purple-800';
                    },
                    getDutyColor(duty) {
                        if (duty === 'OFF') return 'bg-gray-200 text-gray-400 italic';
                        if (duty === 'BREAK') return 'bg-amber-100 text-amber-800 font-bold';
                        return 'bg-blue-50 text-blue-700 font-bold';
                    },
                    getSchedCell(day, empId, hour) {
                        try { return this.scheduleObj.data[day][empId][hour] || 'OFF'; } catch(e) { return 'OFF'; }
                    },
                    updateSchedCell(day, empId, hour, channel) {
                        if (this.currentUser.role === 'USER') {
                            alert("⛔ Nhân viên không có quyền chỉnh sửa ca trực!");
                            return;
                        }
                        this.pendingEdit = { day, empId, hour, channel };
                        if (['PUBLISHED', 'LOCKED'].includes(this.scheduleObj.status)) {
                            this.editReason = '';
                            this.showReasonModal = true;
                        } else {
                            this.confirmUpdateSchedCell();
                        }
                    },
                    async confirmUpdateSchedCell() {
                        let payload = { 
                            day: this.pendingEdit.day, 
                            emp_id: this.pendingEdit.empId, 
                            hour: parseInt(this.pendingEdit.hour), 
                            channel: this.pendingEdit.channel, 
                            reason: this.editReason,
                            actor_role: this.currentUser.role 
                        };
                        let res = await fetch('/api/v1/admin/schedule/update-cell', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        if (res.ok) {
                            let result = await res.json();
                            if (result.success) {
                                this.scheduleObj = result.schedule;
                                this.showReasonModal = false;
                                this.editReason = '';
                                this.loadAllData();
                            }
                        } else {
                            let err = await res.json();
                            alert(err.detail || "Có lỗi xảy ra khi cập nhật lịch!");
                        }
                    },
                    async changeScheduleStatus(newStatus) {
                        if (this.currentUser.role === 'USER') return;
                        let res = await (await fetch('/api/v1/admin/schedule/status', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ status: newStatus })
                        })).json();
                        if (res.success) { this.scheduleObj = res.schedule; this.loadAllData(); }
                    },
                    async runAutoScheduler() {
                        if (this.currentUser.role === 'USER') return;
                        if (!confirm('Chạy thuật toán Auto-Scheduler chuẩn WFM?')) return;
                        let res = await (await fetch('/api/v1/admin/schedule/auto-scheduler', { method: 'POST' })).json();
                        if (res.success) { this.scheduleObj = res.schedule; alert(res.message); this.loadAllData(); }
                    },
                    openCreateModal() {
                        this.isEditMode = false;
                        this.userForm = { id: 'EMP0' + (this.usersList.length + 5), full_name: '', password: '123', role: 'USER', status: 'ACTIVE', team: 'Team CSKH 1' };
                        this.showUserModal = true;
                    },
                    editUser(u) {
                        this.isEditMode = true;
                        this.userForm = { ...u, password: '' };
                        this.showUserModal = true;
                    },
                    async saveUser() {
                        let url = this.isEditMode ? `/api/v1/admin/users/${this.userForm.id}` : '/api/v1/admin/users';
                        let res = await (await fetch(url, {
                            method: this.isEditMode ? 'PUT' : 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(this.userForm)
                        })).json();
                        if (res.success) { this.usersList = res.users; this.showUserModal = false; this.loadAllData(); alert('Thành công!'); }
                    },
                    async deleteUser(empId) {
                        if (confirm('Khóa nhân sự này?')) {
                            let res = await (await fetch(`/api/v1/admin/users/${empId}`, { method: 'DELETE' })).json();
                            if (res.success) { this.usersList = res.users; this.loadAllData(); }
                        }
                    },
                    async restoreUser(empId) {
                        let res = await (await fetch(`/api/v1/admin/users/${empId}/restore`, { method: 'POST' })).json();
                        if (res.success) { this.usersList = res.users; this.loadAllData(); alert('Đã khôi phục!'); }
                    },
                    openEditSkill(sk) {
                        this.skillForm = JSON.parse(JSON.stringify(sk));
                        this.showSkillModal = true;
                        this.showSkillModalFlag = true;
                    },
                    async saveSkill() {
                        let res = await (await fetch(`/api/v1/admin/skills/${this.skillForm.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ level: this.skillForm.level, skills: this.skillForm.skills })
                        })).json();
                        if (res.success) { 
                            this.skillsList = res.skills; 
                            this.showSkillModal = false; 
                            this.showSkillModalFlag = false; 
                            this.loadAllData(); 
                            alert('Cập nhật kỹ năng thành công!'); 
                        }
                    },
                    async uploadCsv(e) {
                        let file = e.target.files[0];
                        if (!file) return;
                        let fd = new FormData(); fd.append('file', file);
                        let res = await (await fetch('/api/v1/admin/users/import-csv', { method: 'POST', body: fd })).json();
                        if (res.success) { this.usersList = res.users; this.loadAllData(); alert(res.message); }
                        e.target.value = '';
                    }
                }
            }
        </script>
    </body>
    </html>
    """