import os
import psycopg2
from psycopg2 import extras
from typing import List, Dict, Optional, Tuple, Any, Union
import streamlit as st
from datetime import datetime
import json
from pathlib import Path

# تهيئة الاتصال بقاعدة بيانات Neon.tech (PostgreSQL)
# يفضل استخدام متغيرات البيئة لتخزين بيانات الاعتماد الحساسة
DB_HOST = os.environ.get("NEON_DB_HOST", "YOUR_NEON_HOST")
DB_DATABASE = os.environ.get("NEON_DB_DATABASE", "YOUR_NEON_DATABASE")
DB_USER = os.environ.get("NEON_DB_USER", "YOUR_NEON_USER")
DB_PASSWORD = os.environ.get("NEON_DB_PASSWORD", "YOUR_NEON_PASSWORD")
DB_PORT = os.environ.get("NEON_DB_PORT", "5432")

def get_db_connection():
    """إنشاء اتصال جديد بقاعدة البيانات."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_DATABASE,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            sslmode='require' # هذا مهم جداً لـ Neon.tech
        )
        return conn
    except Exception as e:
        st.error(f"خطأ في الاتصال بقاعدة البيانات: {str(e)}")
        return None

def execute_query(query: str, params: Optional[Tuple] = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False):
    """
    دالة مساعدة لتنفيذ استعلامات SQL.
    تستخدم psycopg2.extras.RealDictCursor لجلب النتائج كقاموس.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if commit:
                conn.commit()
                return True
            elif fetch_one:
                return cur.fetchone()
            elif fetch_all:
                return cur.fetchall()
            else:
                return True # For INSERT, UPDATE, DELETE operations without fetching
    except Exception as e:
        st.error(f"حدث خطأ في تنفيذ الاستعلام: {str(e)}")
        if conn:
            conn.rollback() # Rollback in case of error
        return None
    finally:
        if conn:
            conn.close()

def get_user_by_username(username: str) -> Optional[Dict]:
    """الحصول على معلومات المستخدم بواسطة اسم المستخدم."""
    query = """
    SELECT
        u.user_id,
        u.username,
        u.password_hash,
        u.role,
        u.region_id as assigned_region,  # تغيير هنا من assigned_region إلى region_id
        u.last_login,
        ha.admin_name AS health_admin_name,
        g.governorate_name AS governorate_admin_governorate_name
    FROM
        Users u
    LEFT JOIN
        HealthAdministrations ha ON u.region_id = ha.admin_id  # تغيير هنا أيضاً
    LEFT JOIN
        GovernorateAdmins ga ON u.user_id = ga.user_id
    LEFT JOIN
        Governorates g ON ga.governorate_id = g.governorate_id
    WHERE
        u.username = %s;
    """
    user_data = execute_query(query, (username,), fetch_one=True)
    if user_data:
        # إعادة هيكلة البيانات لتتوافق مع التنسيق المتوقع في باقي الكود
        user_dict = dict(user_data)
        if user_dict.get('health_admin_name'):
            user_dict['HealthAdministrations'] = {'admin_name': user_dict['health_admin_name']}
        if user_dict.get('governorate_admin_governorate_name'):
            user_dict['GovernorateAdmins'] = {'Governorates': {'governorate_name': user_dict['governorate_admin_governorate_name']}}
        return user_dict
    return None

def get_user_role(user_id: int) -> Optional[str]:
    """الحصول على دور المستخدم."""
    query = "SELECT role FROM Users WHERE user_id = %s;"
    result = execute_query(query, (user_id,), fetch_one=True)
    return result['role'] if result else None

def add_user(username: str, password: str, role: str, region_id: Optional[int] = None) -> bool:
    """إضافة مستخدم جديد."""
    from auth import hash_password # يجب أن تكون هذه الدالة موجودة في auth.py
    hashed_password = hash_password(password)
    query = "INSERT INTO Users (username, password_hash, role, assigned_region) VALUES (%s, %s, %s, %s) RETURNING user_id;"
    result = execute_query(query, (username, hashed_password, role, region_id), fetch_one=True, commit=True)
    return bool(result)

def update_user(user_id: int, username: str, role: str, region_id: Optional[int] = None) -> bool:
    """تحديث بيانات المستخدم."""
    query = "UPDATE Users SET username = %s, role = %s, assigned_region = %s WHERE user_id = %s;"
    return execute_query(query, (username, role, region_id, user_id), commit=True)

def get_health_admins() -> List[Tuple[int, str]]:
    """استرجاع جميع الإدارات الصحية."""
    query = "SELECT admin_id, admin_name FROM HealthAdministrations;"
    results = execute_query(query, fetch_all=True)
    return [(item['admin_id'], item['admin_name']) for item in results] if results else []

def get_health_admin_name(admin_id: int) -> str:
    """استرجاع اسم الإدارة الصحية."""
    if admin_id is None:
        return "غير معين"
    query = "SELECT admin_name FROM HealthAdministrations WHERE admin_id = %s;"
    result = execute_query(query, (admin_id,), fetch_one=True)
    return result['admin_name'] if result else "غير معروف"

def save_response(survey_id: int, user_id: int, region_id: int, is_completed: bool = False) -> Optional[int]:
    """حفظ استجابة جديدة."""
    query = "INSERT INTO Responses (survey_id, user_id, region_id, is_completed, submission_date) VALUES (%s, %s, %s, %s, NOW()) RETURNING response_id;"
    result = execute_query(query, (survey_id, user_id, region_id, is_completed), fetch_one=True, commit=True)
    return result['response_id'] if result else None

def save_response_detail(response_id: int, field_id: int, answer_value: str) -> bool:
    """حفظ تفاصيل الإجابة."""
    query = "INSERT INTO Response_Details (response_id, field_id, answer_value) VALUES (%s, %s, %s);"
    return execute_query(query, (response_id, field_id, str(answer_value)), commit=True)

def save_survey(survey_name: str, fields: List[Dict], governorate_ids: List[int]) -> bool:
    """حفظ استبيان جديد مع حقوله وربطه بالمحافظات."""
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # إدراج الاستبيان الأساسي
            survey_query = "INSERT INTO Surveys (survey_name, created_by, created_at) VALUES (%s, %s, NOW()) RETURNING survey_id;"
            cur.execute(survey_query, (survey_name, st.session_state.user_id))
            survey_id = cur.fetchone()['survey_id']

            # إدراج حقول الاستبيان
            for i, field in enumerate(fields):
                field_data = {
                    'survey_id': survey_id,
                    'field_label': field['field_label'],
                    'field_type': field['field_type'],
                    'field_options': json.dumps(field.get('field_options', [])),
                    'is_required': field.get('is_required', False),
                    'field_order': i # استخدام الترتيب من القائمة
                }
                field_query = """
                INSERT INTO Survey_Fields (survey_id, field_label, field_type, field_options, is_required, field_order)
                VALUES (%(survey_id)s, %(field_label)s, %(field_type)s, %(field_options)s, %(is_required)s, %(field_order)s);
                """
                cur.execute(field_query, field_data)

            # ربط الاستبيان بالمحافظات
            for gov_id in governorate_ids:
                gov_link_query = "INSERT INTO SurveyGovernorate (survey_id, governorate_id) VALUES (%s, %s);"
                cur.execute(gov_link_query, (survey_id, gov_id))
            
            conn.commit()
            st.success("تم حفظ الاستبيان بنجاح.")
            return True
    except Exception as e:
        st.error(f"حدث خطأ في حفظ الاستبيان: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def update_last_login(user_id: int):
    """تحديث وقت آخر دخول للمستخدم."""
    query = "UPDATE Users SET last_login = NOW() WHERE user_id = %s;"
    execute_query(query, (user_id,), commit=True)

def update_user_activity(user_id: int):
    """تحديث نشاط المستخدم."""
    query = "UPDATE Users SET last_activity = NOW() WHERE user_id = %s;"
    execute_query(query, (user_id,), commit=True)

def delete_survey(survey_id: int) -> bool:
    """حذف استبيان وجميع بياناته المرتبطة."""
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        with conn.cursor() as cur:
            # حذف تفاصيل الإجابات المرتبطة
            cur.execute("DELETE FROM Response_Details WHERE response_id IN (SELECT response_id FROM Responses WHERE survey_id = %s);", (survey_id,))
            # حذف الإجابات المرتبطة
            cur.execute("DELETE FROM Responses WHERE survey_id = %s;", (survey_id,))
            # حذف حقول الاستبيان
            cur.execute("DELETE FROM Survey_Fields WHERE survey_id = %s;", (survey_id,))
            # حذف روابط المحافظات
            cur.execute("DELETE FROM SurveyGovernorate WHERE survey_id = %s;", (survey_id,))
            # حذف الاستبيان نفسه
            cur.execute("DELETE FROM Surveys WHERE survey_id = %s;", (survey_id,))
            conn.commit()
            st.success("تم حذف الاستبيان بنجاح")
            return True
    except Exception as e:
        st.error(f"حدث خطأ أثناء حذف الاستبيان: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def add_health_admin(admin_name: str, description: str, governorate_id: int) -> bool:
    """إضافة إدارة صحية جديدة."""
    # التحقق من التكرار
    check_query = "SELECT admin_id FROM HealthAdministrations WHERE admin_name = %s AND governorate_id = %s;"
    existing = execute_query(check_query, (admin_name, governorate_id), fetch_one=True)
    if existing:
        st.error("هذه الإدارة الصحية موجودة بالفعل في هذه المحافظة!")
        return False

    # إضافة الإدارة الجديدة
    insert_query = "INSERT INTO HealthAdministrations (admin_name, description, governorate_id) VALUES (%s, %s, %s);"
    return execute_query(insert_query, (admin_name, description, governorate_id), commit=True)

def get_governorates_list() -> List[Dict]:
    """استرجاع قائمة المحافظات."""
    query = "SELECT governorate_id, governorate_name, description FROM Governorates;"
    results = execute_query(query, fetch_all=True)
    return results if results else []

def update_survey(survey_id: int, survey_name: str, is_active: bool, fields: List[Dict]) -> bool:
    """تحديث بيانات الاستبيان وحقوله."""
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # تحديث بيانات الاستبيان الأساسية
            survey_update_query = "UPDATE Surveys SET survey_name = %s, is_active = %s WHERE survey_id = %s;"
            cur.execute(survey_update_query, (survey_name, is_active, survey_id))

            # جلب الحقول الموجودة حالياً لتحديد ما يجب حذفه
            existing_field_ids_query = "SELECT field_id FROM Survey_Fields WHERE survey_id = %s;"
            cur.execute(existing_field_ids_query, (survey_id,))
            existing_field_ids = {f['field_id'] for f in cur.fetchall()}

            updated_field_ids = {f['field_id'] for f in fields if 'field_id' in f}
            fields_to_delete = existing_field_ids - updated_field_ids

            # حذف الحقول التي لم تعد موجودة
            if fields_to_delete:
                delete_fields_query = "DELETE FROM Survey_Fields WHERE field_id = ANY(%s);"
                cur.execute(delete_fields_query, (list(fields_to_delete),))

            # تحديث الحقول الموجودة أو إضافة جديدة
            for i, field in enumerate(fields):
                field_options = json.dumps(field.get('field_options', [])) if field.get('field_options') else None
                
                if 'field_id' in field:  # حقل موجود يتم تحديثه
                    update_field_query = """
                    UPDATE Survey_Fields SET
                        field_label = %s,
                        field_type = %s,
                        field_options = %s,
                        is_required = %s,
                        field_order = %s
                    WHERE field_id = %s;
                    """
                    cur.execute(update_field_query, (
                        field['field_label'], field['field_type'], field_options,
                        field.get('is_required', False), i, field['field_id']
                    ))
                else:  # حقل جديد يتم إضافته
                    insert_field_query = """
                    INSERT INTO Survey_Fields (survey_id, field_label, field_type, field_options, is_required, field_order)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """
                    cur.execute(insert_field_query, (
                        survey_id, field['field_label'], field['field_type'], field_options,
                        field.get('is_required', False), i
                    ))
            
            conn.commit()
            st.success("تم تحديث الاستبيان بنجاح")
            return True
    except Exception as e:
        st.error(f"حدث خطأ في تحديث الاستبيان: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def add_governorate_admin(user_id: int, governorate_id: int) -> bool:
    """إضافة مسؤول محافظة جديد."""
    query = "INSERT INTO GovernorateAdmins (user_id, governorate_id) VALUES (%s, %s);"
    return execute_query(query, (user_id, governorate_id), commit=True)

def get_governorate_admin_data(user_id: int) -> Optional[Tuple]:
    """الحصول على بيانات المحافظة لمسؤول المحافظة."""
    query = """
    SELECT
        g.governorate_id,
        g.governorate_name,
        g.description
    FROM
        GovernorateAdmins ga
    JOIN
        Governorates g ON ga.governorate_id = g.governorate_id
    WHERE
        ga.user_id = %s;
    """
    result = execute_query(query, (user_id,), fetch_one=True)
    if result:
        return (result['governorate_id'], result['governorate_name'], result['description'])
    return None

def get_governorate_surveys(governorate_id: int) -> List[Tuple[int, str, str, bool]]:
    """الحصول على الاستبيانات الخاصة بمحافظة معينة."""
    query = """
    SELECT
        s.survey_id,
        s.survey_name,
        s.created_at,
        s.is_active
    FROM
        SurveyGovernorate sg
    JOIN
        Surveys s ON sg.survey_id = s.survey_id
    WHERE
        sg.governorate_id = %s;
    """
    results = execute_query(query, (governorate_id,), fetch_all=True)
    return [(item['survey_id'], item['survey_name'], str(item['created_at']), item['is_active']) for item in results] if results else []

def get_governorate_employees(governorate_id: int) -> List[Tuple[int, str, str]]:
    """الحصول على الموظفين التابعين لمحافظة معينة."""
    query = """
    SELECT
        u.user_id,
        u.username,
        ha.admin_name
    FROM
        Users u
    JOIN
        HealthAdministrations ha ON u.assigned_region = ha.admin_id
    WHERE
        u.role = 'employee' AND ha.governorate_id = %s;
    """
    results = execute_query(query, (governorate_id,), fetch_all=True)
    return [(item['user_id'], item['username'], item['admin_name']) for item in results] if results else []

def get_allowed_surveys(user_id: int) -> List[Dict]:
    """الحصول على الاستبيانات المسموح بها للموظف (بناءً على المحافظة)."""
    query = """
    SELECT
        s.survey_id,
        s.survey_name
    FROM
        Users u
    JOIN
        HealthAdministrations ha ON u.assigned_region = ha.admin_id
    JOIN
        SurveyGovernorate sg ON ha.governorate_id = sg.governorate_id
    JOIN
        Surveys s ON sg.survey_id = s.survey_id
    WHERE
        u.user_id = %s AND s.is_active = TRUE;
    """
    results = execute_query(query, (user_id,), fetch_all=True)
    return results if results else []

def get_survey_fields(survey_id: int) -> List[Tuple[int, str, str, str, bool, int]]:
    """الحصول على حقول استبيان معين."""
    query = "SELECT field_id, field_label, field_type, field_options, is_required, field_order FROM Survey_Fields WHERE survey_id = %s ORDER BY field_order;"
    results = execute_query(query, (survey_id,), fetch_all=True)
    return [(item['field_id'], item['field_label'], item['field_type'],
             item['field_options'], item['is_required'], item['field_order'])
            for item in results] if results else []

def get_user_allowed_surveys(user_id: int) -> List[Tuple[int, str]]:
    """الحصول على الاستبيانات المسموح بها للمستخدم (من جدول UserSurveys)."""
    query = """
    SELECT
        s.survey_id,
        s.survey_name
    FROM
        UserSurveys us
    JOIN
        Surveys s ON us.survey_id = s.survey_id
    WHERE
        us.user_id = %s;
    """
    results = execute_query(query, (user_id,), fetch_all=True)
    return [(item['survey_id'], item['survey_name']) for item in results] if results else []

def update_user_allowed_surveys(user_id: int, survey_ids: List[int]) -> bool:
    """تحديث الاستبيانات المسموح بها للمستخدم."""
    try:
        conn = get_db_connection()
        if conn is None:
            return False
        with conn.cursor() as cur:
            # حذف جميع التصاريح الحالية
            cur.execute("DELETE FROM UserSurveys WHERE user_id = %s;", (user_id,))
            
            # إضافة التصاريح الجديدة
            for survey_id in survey_ids:
                cur.execute("INSERT INTO UserSurveys (user_id, survey_id) VALUES (%s, %s);", (user_id, survey_id))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"حدث خطأ في تحديث الاستبيانات المسموح بها: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_response_details(response_id: int) -> List[Tuple[int, int, str, str, str, str]]:
    """الحصول على تفاصيل إجابة محددة."""
    query = """
    SELECT
        rd.detail_id,
        rd.field_id,
        sf.field_label,
        sf.field_type,
        sf.field_options,
        rd.answer_value
    FROM
        Response_Details rd
    JOIN
        Survey_Fields sf ON rd.field_id = sf.field_id
    WHERE
        rd.response_id = %s;
    """
    results = execute_query(query, (response_id,), fetch_all=True)
    return [(item['detail_id'], item['field_id'], item['field_label'],
             item['field_type'], item['field_options'], item['answer_value'])
            for item in results] if results else []

def update_response_detail(detail_id: int, new_value: str) -> bool:
    """تحديث قيمة إجابة محددة."""
    query = "UPDATE Response_Details SET answer_value = %s WHERE detail_id = %s;"
    return execute_query(query, (new_value, detail_id), commit=True)

def get_response_info(response_id: int) -> Optional[Tuple[int, str, str, str, str, str]]:
    """الحصول على معلومات أساسية عن الإجابة."""
    query = """
    SELECT
        r.response_id,
        s.survey_name,
        u.username,
        ha.admin_name,
        g.governorate_name,
        r.submission_date
    FROM
        Responses r
    JOIN
        Surveys s ON r.survey_id = s.survey_id
    JOIN
        Users u ON r.user_id = u.user_id
    JOIN
        HealthAdministrations ha ON r.region_id = ha.admin_id
    JOIN
        Governorates g ON ha.governorate_id = g.governorate_id
    WHERE
        r.response_id = %s;
    """
    result = execute_query(query, (response_id,), fetch_one=True)
    if result:
        return (
            result['response_id'],
            result['survey_name'],
            result['username'],
            result['admin_name'],
            result['governorate_name'],
            str(result['submission_date']) # تحويل datetime إلى string
        )
    return None

def log_audit_action(user_id: int, action_type: str, table_name: str,
                    record_id: int = None, old_value: Any = None,
                    new_value: Any = None) -> bool:
    """تسجيل إجراء في سجل التعديلات."""
    query = """
    INSERT INTO AuditLog (user_id, action_type, table_name, record_id, old_value, new_value, action_timestamp)
    VALUES (%s, %s, %s, %s, %s, %s, NOW());
    """
    return execute_query(query, (user_id, action_type, table_name, record_id,
                                 json.dumps(old_value) if old_value else None,
                                 json.dumps(new_value) if new_value else None), commit=True)

def get_audit_logs(table_name: str = None, action_type: str = None,
                  username: str = None, date_range: Tuple[str, str] = None,
                  search_query: str = None) -> List[Tuple[int, str, str, str, int, str, str, str]]:
    """الحصول على سجل التعديلات مع فلاتر متقدمة."""
    base_query = """
    SELECT
        al.log_id,
        u.username,
        al.action_type,
        al.table_name,
        al.record_id,
        al.old_value,
        al.new_value,
        al.action_timestamp
    FROM
        AuditLog al
    JOIN
        Users u ON al.user_id = u.user_id
    WHERE 1=1
    """
    params = []
    conditions = []

    if table_name:
        conditions.append("al.table_name = %s")
        params.append(table_name)
    if action_type:
        conditions.append("al.action_type = %s")
        params.append(action_type)
    if username:
        conditions.append("u.username ILIKE %s")
        params.append(f'%{username}%')
    if date_range:
        conditions.append("al.action_timestamp >= %s AND al.action_timestamp <= %s")
        params.extend(date_range)
    if search_query:
        conditions.append("(al.old_value::text ILIKE %s OR al.new_value::text ILIKE %s OR u.username ILIKE %s OR al.table_name ILIKE %s OR al.action_type ILIKE %s)")
        params.extend([f'%{search_query}%'] * 5)

    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    base_query += " ORDER BY al.action_timestamp DESC;"

    results = execute_query(base_query, tuple(params), fetch_all=True)
    return [(item['log_id'], item['username'], item['action_type'],
             item['table_name'], item['record_id'], item['old_value'],
             item['new_value'], str(item['action_timestamp'])) # تحويل datetime إلى string
            for item in results] if results else []

def has_completed_survey_today(user_id: int, survey_id: int) -> bool:
    """التحقق مما إذا كان المستخدم قد أكمل استبيانًا معينًا اليوم."""
    query = """
    SELECT
        response_id
    FROM
        Responses
    WHERE
        user_id = %s AND survey_id = %s AND is_completed = TRUE
        AND submission_date::date = CURRENT_DATE;
    """
    result = execute_query(query, (user_id, survey_id), fetch_one=True)
    return bool(result)

# إضافة دوال إدارة المحافظات والإدارات الصحية التي كانت موجودة في Supabase
def add_governorate(governorate_name: str, description: str) -> bool:
    """إضافة محافظة جديدة."""
    query = "INSERT INTO Governorates (governorate_name, description) VALUES (%s, %s);"
    return execute_query(query, (governorate_name, description), commit=True)

def update_governorate(governorate_id: int, new_name: str, new_desc: str) -> bool:
    """تحديث بيانات محافظة موجودة."""
    query = "UPDATE Governorates SET governorate_name = %s, description = %s WHERE governorate_id = %s;"
    return execute_query(query, (new_name, new_desc, governorate_id), commit=True)

def delete_governorate(governorate_id: int) -> bool:
    """حذف محافظة."""
    # التحقق مما إذا كانت هناك إدارات صحية مرتبطة
    check_regions_query = "SELECT admin_id FROM HealthAdministrations WHERE governorate_id = %s;"
    has_regions = execute_query(check_regions_query, (governorate_id,), fetch_one=True)
    if has_regions:
        st.error("لا يمكن حذف المحافظة لأنها تحتوي على إدارات صحية!")
        return False
    
    query = "DELETE FROM Governorates WHERE governorate_id = %s;"
    return execute_query(query, (governorate_id,), commit=True)

def update_health_admin(admin_id: int, new_name: str, new_desc: str, new_gov_id: int) -> bool:
    """تحديث بيانات إدارة صحية."""
    query = "UPDATE HealthAdministrations SET admin_name = %s, description = %s, governorate_id = %s WHERE admin_id = %s;"
    return execute_query(query, (new_name, new_desc, new_gov_id, admin_id), commit=True)

def delete_health_admin(admin_id: int) -> bool:
    """حذف إدارة صحية."""
    # التحقق مما إذا كان هناك مستخدمون مرتبطون
    check_users_query = "SELECT user_id FROM Users WHERE assigned_region = %s;"
    has_users = execute_query(check_users_query, (admin_id,), fetch_one=True)
    if has_users:
        st.error("لا يمكن حذف الإدارة الصحية لأنها مرتبطة بمستخدمين!")
        return False
    
    query = "DELETE FROM HealthAdministrations WHERE admin_id = %s;"
    return execute_query(query, (admin_id,), commit=True)

def get_governorate_by_id(gov_id: int) -> Optional[Dict]:
    """الحصول على بيانات محافظة بواسطة ID."""
    query = "SELECT governorate_id, governorate_name, description FROM Governorates WHERE governorate_id = %s;"
    return execute_query(query, (gov_id,), fetch_one=True)

def get_health_admin_by_id(admin_id: int) -> Optional[Dict]:
    """الحصول على بيانات إدارة صحية بواسطة ID."""
    query = "SELECT admin_id, admin_name, description, governorate_id FROM HealthAdministrations WHERE admin_id = %s;"
    return execute_query(query, (admin_id,), fetch_one=True)

def get_responses_for_survey(survey_id: int) -> List[Dict]:
    """الحصول على جميع الإجابات لاستبيان معين."""
    query = """
    SELECT
        r.response_id,
        u.username,
        ha.admin_name,
        g.governorate_name,
        r.submission_date,
        r.is_completed
    FROM
        Responses r
    JOIN
        Users u ON r.user_id = u.user_id
    JOIN
        HealthAdministrations ha ON r.region_id = ha.admin_id
    JOIN
        Governorates g ON ha.governorate_id = g.governorate_id
    WHERE
        r.survey_id = %s;
    """
    return execute_query(query, (survey_id,), fetch_all=True)

def get_survey_by_id(survey_id: int) -> Optional[Dict]:
    """الحصول على بيانات استبيان بواسطة ID."""
    query = "SELECT survey_id, survey_name, created_at, is_active FROM Surveys WHERE survey_id = %s;"
    return execute_query(query, (survey_id,), fetch_one=True)

def get_user_data_for_admin_view(user_id: int) -> Optional[Dict]:
    """
    الحصول على بيانات المستخدم لعرضها في لوحة تحكم المسؤول،
    مع جلب اسم المحافظة والإدارة الصحية المرتبطة.
    """
    query = """
    SELECT
        u.user_id,
        u.username,
        u.role,
        u.assigned_region,
        g.governorate_name,
        ha.admin_name
    FROM
        Users u
    LEFT JOIN
        GovernorateAdmins ga ON u.user_id = ga.user_id
    LEFT JOIN
        Governorates g ON ga.governorate_id = g.governorate_id OR (u.assigned_region IS NOT NULL AND u.assigned_region = ha.admin_id AND ha.governorate_id = g.governorate_id)
    LEFT JOIN
        HealthAdministrations ha ON u.assigned_region = ha.admin_id
    WHERE
        u.user_id = %s;
    """
    user_data = execute_query(query, (user_id,), fetch_one=True)
    if user_data:
        # التأكد من أن المفاتيح موجودة حتى لو كانت القيم None
        user_data['governorate_name'] = user_data.get('governorate_name')
        user_data['admin_name'] = user_data.get('admin_name')
    return user_data

def get_all_users_for_admin_view() -> List[Dict]:
    """
    الحصول على جميع المستخدمين لعرضهم في لوحة تحكم المسؤول،
    مع جلب اسم المحافظة والإدارة الصحية المرتبطة.
    """
    query = """
    SELECT
        u.user_id,
        u.username,
        u.role,
        u.assigned_region,
        COALESCE(g_gov_admin.governorate_name, g_employee.governorate_name) AS governorate_name,
        ha.admin_name
    FROM
        Users u
    LEFT JOIN
        GovernorateAdmins ga ON u.user_id = ga.user_id
    LEFT JOIN
        Governorates g_gov_admin ON ga.governorate_id = g_gov_admin.governorate_id
    LEFT JOIN
        HealthAdministrations ha ON u.assigned_region = ha.admin_id
    LEFT JOIN
        Governorates g_employee ON ha.governorate_id = g_employee.governorate_id
    ORDER BY u.username;
    """
    return execute_query(query, fetch_all=True)

