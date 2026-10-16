import pytest
from bot.database import Database
from bot.handlers.common import user_in_lecturer_scope, lecturer_class_ids

def test_lecturer_class_ids_and_scope():
    # 1. Test Guru Besar - gets all teaching_classes
    prof_guru_besar = {
        "bem_position": ["d_guru_besar"],
        "teaching_classes": ["umum_kk", "if101"]
    }
    assert set(lecturer_class_ids(prof_guru_besar)) == {"umum_kk", "if101"}

    # 2. Test Dosen without staff_major
    prof_dosen_no_major = {
        "bem_position": ["d_dosen"],
        "teaching_classes": ["umum_pd"]
    }
    assert set(lecturer_class_ids(prof_dosen_no_major)) == {"umum_pd"}

    # 3. Test Dosen with staff_major (ik = Kimia). 'ik' classes should auto-assign.
    # Choices in choices.yaml: classes with majors == "ik" would auto-assign!
    # Wait, the config is real, so if there are classes with majors "ik", they get added.
    prof_dosen_major = {
        "bem_position": ["d_dosen"],
        "staff_major": "ik",
        "teaching_classes": ["umum_pd"] # manual addition
    }
    c_ids = lecturer_class_ids(prof_dosen_major)
    # We should have "umum_pd" and any class that has major="ik"
    assert "umum_pd" in c_ids
    
    # 4. Test Coach (UKM)
    prof_coach = {
        "bem_position": ["d_coach"],
        "club_enrolled": ["ui", "uk"]
    }
    assert set(lecturer_class_ids(prof_coach)) == {"ui", "uk"}

    # 5. Test Panitia Ospek
    prof_panitia = {
        "bem_position": ["p_panitia_ospek"]
    }
    assert set(lecturer_class_ids(prof_panitia)) == {"ospek_maba"}

    # 6. Scope Testing
    target_classes = ["umum_kk", "if101"]
    
    # User who is enrolled in umum_kk
    prof_student = {
        "class_enrolled": ["umum_kk"]
    }
    assert user_in_lecturer_scope(prof_student, target_classes) is True

    # User who is teaching if101
    prof_teacher = {
        "teaching_classes": ["if101"]
    }
    assert user_in_lecturer_scope(prof_teacher, target_classes) is True
    
    # User who is in club um (not in target)
    prof_other = {
        "club_enrolled": ["um"]
    }
    assert user_in_lecturer_scope(prof_other, target_classes) is False

    # 7. Student with major 'sf' (Dasar Fotografi 'df', Teknik Fotografi 'tf')
    # Lecturer teaching 'df'
    prof_student_major_sf = {
        "major": "sf"
    }
    assert user_in_lecturer_scope(prof_student_major_sf, ["df"]) is True
    assert user_in_lecturer_scope(prof_student_major_sf, ["tf"]) is True
    assert user_in_lecturer_scope(prof_student_major_sf, ["kd"]) is False


def test_maba_and_student_enrolled_class_ids():
    from bot.handlers.common import student_enrolled_class_ids, user_in_dean_faculty_scope
    from bot.handlers.tugas import _student_enrolled_class_ids
    from bot.database import ROLE_MABA, ROLE_STUDENT

    # MABA only gets ospek_maba, never umum or major classes
    maba_prof = {"join_reason": "mau belajar"}
    maba_classes = student_enrolled_class_ids(maba_prof, role=ROLE_MABA)
    assert set(maba_classes) == {"ospek_maba"}

    # MABA in tugas dashboard only gets ospek_maba (+ club if any)
    maba_tugas_classes = _student_enrolled_class_ids(maba_prof, role=ROLE_MABA)
    assert set(maba_tugas_classes) == {"ospek_maba"}

    # Student with major gets umum and major classes, never ospek_maba
    student_prof = {"major": "sf", "faculty": "fib"}
    student_classes = student_enrolled_class_ids(student_prof, role=ROLE_STUDENT)
    assert "df" in student_classes
    assert "tf" in student_classes
    assert "umum_kk" in student_classes
    assert "umum_pd" in student_classes
    assert "ospek_maba" not in student_classes

    # Dekan scope test with staff_faculty
    dekan_staff_prof = {"staff_faculty": "fib"}
    assert user_in_dean_faculty_scope(dekan_staff_prof, "fib") is True
    assert user_in_dean_faculty_scope(dekan_staff_prof, "fmipa") is False


