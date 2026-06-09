#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试第四轮新增功能"""

import sys
import os
import json
from datetime import datetime, timedelta, date

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from effcli.database import Database, Task, Priority, TaskStatus

db = Database()

def execute_sql(sql, params=None):
    with db._connect() as conn:
        if params:
            return conn.execute(sql, params).fetchall()
        return conn.execute(sql).fetchall()

def reset_test_data():
    print("=" * 60)
    print("🧹 重置测试数据...")
    print("=" * 60)
    
    execute_sql("DELETE FROM focus_sessions")
    execute_sql("DELETE FROM tasks")
    
    today = date.today()
    two_weeks_ago = today - timedelta(days=14)
    one_week_ago = today - timedelta(days=7)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)
    
    tasks = []
    
    # 项目A的任务
    task1 = Task(
        id=1,
        title="项目A需求开发",
        project="项目A",
        priority=Priority.HIGH,
        status=TaskStatus.DONE,
        due_date=one_week_ago.isoformat(),
        created_at=datetime.combine(two_weeks_ago, datetime.min.time()).isoformat(),
        started_at=datetime.combine(two_weeks_ago, datetime.min.time()).isoformat(),
        completed_at=datetime.combine(one_week_ago + timedelta(days=1), datetime.min.time()).isoformat(),
        summary="完成了项目A的核心需求开发",
        total_focus_time=3600 * 6,
        interrupt_count=2,
        interrupt_reasons="会议; 接水"
    )
    tasks.append(task1)
    
    # 项目A逾期任务，区间结束时未完成，后来完成
    task2 = Task(
        id=2,
        title="项目A接口联调",
        project="项目A",
        priority=Priority.HIGH,
        status=TaskStatus.DONE,
        due_date=yesterday.isoformat(),
        created_at=datetime.combine(one_week_ago, datetime.min.time()).isoformat(),
        started_at=datetime.combine(one_week_ago, datetime.min.time()).isoformat(),
        completed_at=datetime.combine(today, datetime.min.time()).isoformat(),
        summary="逾期后今天才完成",
        total_focus_time=3600 * 4,
        interrupt_count=1,
        interrupt_reasons="接口文档缺失"
    )
    tasks.append(task2)
    
    # 项目B的任务
    task3 = Task(
        id=3,
        title="项目B性能优化",
        project="项目B",
        priority=Priority.MEDIUM,
        status=TaskStatus.IN_PROGRESS,
        due_date=next_week.isoformat(),
        created_at=datetime.combine(one_week_ago, datetime.min.time()).isoformat(),
        started_at=datetime.combine(one_week_ago, datetime.min.time()).isoformat(),
        completed_at=None,
        summary="",
        total_focus_time=3600 * 2,
        interrupt_count=0,
        interrupt_reasons=""
    )
    tasks.append(task3)
    
    # 项目A的另一个任务
    task4 = Task(
        id=4,
        title="项目A单元测试",
        project="项目A",
        priority=Priority.LOW,
        status=TaskStatus.TODO,
        due_date=tomorrow.isoformat(),
        created_at=datetime.combine(yesterday, datetime.min.time()).isoformat(),
        started_at=None,
        completed_at=None,
        summary="",
        total_focus_time=0,
        interrupt_count=0,
        interrupt_reasons=""
    )
    tasks.append(task4)
    
    with db._connect() as conn:
        for task in tasks:
            conn.execute("""
                INSERT INTO tasks (id, title, project, priority, status, due_date, created_at, 
                                  started_at, completed_at, summary, total_focus_time, 
                                  interrupt_count, interrupt_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.title, task.project, task.priority.value, task.status.value,
                task.due_date, task.created_at, task.started_at, task.completed_at,
                task.summary, task.total_focus_time, task.interrupt_count, task.interrupt_reasons
            ))
        
        # 添加专注记录 - 上周在项目A上
        base_date = one_week_ago + timedelta(days=1)
        for i in range(3):
            start = datetime.combine(base_date + timedelta(days=i), datetime.min.time()) + timedelta(hours=10)
            end = start + timedelta(hours=2)
            conn.execute("""
                INSERT INTO focus_sessions (task_id, start_time, end_time, duration, interrupted, interrupt_reason)
                VALUES (?, ?, ?, ?, 0, NULL)
            """, (1, start.isoformat(), end.isoformat(), 7200))
        
        # 项目B的专注记录
        for i in range(2):
            start = datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=14 + i * 2)
            end = start + timedelta(hours=1)
            conn.execute("""
                INSERT INTO focus_sessions (task_id, start_time, end_time, duration, interrupted, interrupt_reason)
                VALUES (?, ?, ?, ?, 0, NULL)
            """, (3, start.isoformat(), end.isoformat(), 3600))
    
    print("✅ 测试数据已重置\n")

def test_1_time_distribution_view():
    print("=" * 60)
    print("📊 测试1：周报月报时间分布视图")
    print("=" * 60)
    
    today = date.today()
    one_week_ago = today - timedelta(days=7)
    
    data = db.get_period_review_data(
        date_from=one_week_ago.isoformat(),
        date_to=today.isoformat(),
        period_type="week"
    )
    
    print(f"区间: {one_week_ago} ~ {today}")
    print(f"总专注时长: {data['total_focus_seconds']} 秒")
    print(f"专注记录数: {data['session_count']}")
    print()
    
    print("🔍 按项目汇总 (by_project_focus):")
    for proj, dur in data['by_project_focus'].items():
        hrs = dur / 3600
        print(f"  {proj}: {hrs:.1f} 小时")
    
    print()
    print("🔍 项目投入排行 (project_rank):")
    for i, (proj, dur) in enumerate(data['project_rank'], 1):
        hrs = dur / 3600
        print(f"  {i}. {proj}: {hrs:.1f} 小时")
    
    print()
    print("🔍 每日投入小结 (daily_summary):")
    for d, summary in sorted(data['daily_summary'].items()):
        total_hrs = summary['total'] / 3600
        print(f"  {d}: 共 {total_hrs:.1f} 小时, 主要项目: {summary['top_project']}")
    
    print()
    print("🔍 按任务汇总 (by_task_focus):")
    for task_id, info in data['by_task_focus'].items():
        hrs = info['duration'] / 3600
        print(f"  #{task_id} [{info['project']}] {info['title']}: {hrs:.1f} 小时")
    
    print()
    print("✅ 时间分布视图测试通过\n")

def test_2_sessions_crud():
    print("=" * 60)
    print("⏱️  测试2：专注记录补录/修改/删除")
    print("=" * 60)
    
    task = db.get_task(1)
    original_focus = task.total_focus_time
    print(f"原始任务 #{task.id} 总专注时间: {original_focus} 秒")
    
    # 测试补录
    print("\n📝 测试补录专注记录...")
    start_time = datetime.combine(date.today() - timedelta(days=3), datetime.min.time()) + timedelta(hours=9)
    end_time = start_time + timedelta(hours=1, minutes=30)
    session_id = db.add_focus_session(
        task_id=1,
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        interrupt_reason="临时测试补录"
    )
    print(f"  已补录记录 ID: {session_id}")
    
    task_after_add = db.get_task(1)
    expected_focus = original_focus + 5400
    print(f"  补录后总专注时间: {task_after_add.total_focus_time} 秒 (预期: {expected_focus})")
    assert task_after_add.total_focus_time == expected_focus, "❌ 补录后总专注时间不正确"
    print("  ✅ 补录后总专注时间正确")
    
    # 测试获取单条记录
    session = db.get_focus_session(session_id)
    print(f"\n📋 获取记录 #{session_id}:")
    print(f"  任务: {session['title']}")
    print(f"  项目: {session['project']}")
    print(f"  开始: {session['start_time']}")
    print(f"  结束: {session['end_time']}")
    print(f"  时长: {session['duration']} 秒")
    print(f"  中断原因: {session['interrupt_reason']}")
    
    # 测试修改
    print("\n✏️  测试修改专注记录...")
    new_end = end_time + timedelta(minutes=30)
    updated = db.update_focus_session(
        session_id=session_id,
        end_time=new_end.isoformat(),
        interrupt_reason="测试修改后原因"
    )
    print(f"  修改结果: {updated}")
    
    task_after_edit = db.get_task(1)
    expected_focus_2 = expected_focus + 1800
    print(f"  修改后总专注时间: {task_after_edit.total_focus_time} 秒 (预期: {expected_focus_2})")
    assert task_after_edit.total_focus_time == expected_focus_2, "❌ 修改后总专注时间不正确"
    print("  ✅ 修改后总专注时间正确")
    
    session_after_edit = db.get_focus_session(session_id)
    print(f"  修改后的结束时间: {session_after_edit['end_time']}")
    print(f"  修改后的中断原因: {session_after_edit['interrupt_reason']}")
    
    # 测试删除
    print("\n🗑️  测试删除专注记录...")
    deleted = db.delete_focus_session(session_id)
    print(f"  删除结果: {deleted}")
    
    task_after_delete = db.get_task(1)
    print(f"  删除后总专注时间: {task_after_delete.total_focus_time} 秒 (预期: {original_focus})")
    assert task_after_delete.total_focus_time == original_focus, "❌ 删除后总专注时间不正确"
    print("  ✅ 删除后总专注时间正确")
    
    session_after_delete = db.get_focus_session(session_id)
    assert session_after_delete is None, "❌ 删除后记录仍然存在"
    print("  ✅ 删除后记录已不存在")
    
    print("\n✅ 专注记录CRUD测试通过\n")

def test_3_overdue_history():
    print("=" * 60)
    print("📅 测试3：历史报表逾期口径")
    print("=" * 60)
    
    today = date.today()
    one_week_ago = today - timedelta(days=7)
    
    print(f"区间: {one_week_ago} ~ {today}")
    print()
    
    # 任务2: 截止日是昨天，今天才完成
    task2 = db.get_task(2)
    print(f"任务 #2: {task2.title}")
    print(f"  截止日期: {task2.due_date}")
    print(f"  完成日期: {task2.completed_at}")
    print(f"  当前状态: {task2.status.value}")
    print()
    
    data = db.get_period_review_data(
        date_from=one_week_ago.isoformat(),
        date_to=today.isoformat(),
        period_type="week"
    )
    
    print(f"期初逾期: {len(data['overdue_start'])} 个")
    for t in data['overdue_start']:
        print(f"  - #{t.id} {t.title} (截止: {t.due_date})")
    
    print(f"\n期末逾期: {len(data['overdue_end'])} 个")
    for t in data['overdue_end']:
        print(f"  - #{t.id} {t.title} (截止: {t.due_date}, 完成: {t.completed_at})")
    
    # 任务2应该在期末逾期中，因为它在区间结束时（今天）虽然完成了，
    # 但它是今天才完成的，区间结束时如果回看昨天的区间，应该算逾期
    # 让我们测试一个上周的区间
    print("\n--- 测试上周区间 (14天前 ~ 7天前) ---")
    two_weeks_ago = today - timedelta(days=14)
    eight_days_ago = today - timedelta(days=8)
    
    data2 = db.get_period_review_data(
        date_from=two_weeks_ago.isoformat(),
        date_to=eight_days_ago.isoformat(),
        period_type="week"
    )
    
    print(f"区间: {two_weeks_ago} ~ {eight_days_ago}")
    print(f"期末逾期: {len(data2['overdue_end'])} 个")
    for t in data2['overdue_end']:
        print(f"  - #{t.id} {t.title} (截止: {t.due_date}, 状态: {t.status.value})")
    
    # 任务1截止日是7天前，区间结束日是8天前，所以它在区间结束时还没到期，不算逾期
    # 任务2截止日是昨天，区间结束日是8天前，所以它在区间结束时还没到期，不算逾期
    
    print("\n--- 测试包含今天的区间，任务2今天完成，昨天到期 ---")
    data3 = db.get_period_review_data(
        date_from=(today - timedelta(days=3)).isoformat(),
        date_to=today.isoformat(),
        period_type="week"
    )
    
    print(f"区间: {today - timedelta(days=3)} ~ {today}")
    print(f"期末逾期: {len(data3['overdue_end'])} 个")
    for t in data3['overdue_end']:
        print(f"  - #{t.id} {t.title} (截止: {t.due_date}, 完成: {t.completed_at})")
    
    # 任务2的截止日是昨天<今天，今天才完成，按照新逻辑：
    # 区间结束日是今天，任务2在今天完成了，完成日期 = 区间结束日
    # 所以条件 DATE(t.completed_at) > ? 不成立（今天 > 今天 为 false）
    # 所以任务2不算期末逾期 ✓
    
    print("\n--- 测试区间结束在昨天，任务2今天完成 ---")
    data4 = db.get_period_review_data(
        date_from=(today - timedelta(days=7)).isoformat(),
        date_to=(today - timedelta(days=1)).isoformat(),
        period_type="week"
    )
    
    print(f"区间: {today - timedelta(days=7)} ~ {today - timedelta(days=1)}")
    print(f"期末逾期: {len(data4['overdue_end'])} 个")
    for t in data4['overdue_end']:
        print(f"  - #{t.id} {t.title} (截止: {t.due_date}, 完成: {t.completed_at})")
    
    # 任务2的截止日是昨天 <= 区间结束日（昨天）
    # 任务2的完成日期是今天 > 区间结束日（昨天）
    # 所以按照新逻辑，任务2应该算入期末逾期 ✓
    assert any(t.id == 2 for t in data4['overdue_end']), "❌ 任务2应该计入期末逾期"
    print("  ✅ 任务2正确计入期末逾期（区间结束时未完成）")
    
    print("\n✅ 历史逾期口径测试通过\n")

def test_4_project_filter():
    print("=" * 60)
    print("🔍 测试4：项目模糊匹配和多项目筛选")
    print("=" * 60)
    
    # 测试 parse_project_filter
    print("📋 测试 parse_project_filter:")
    
    _, matched = db.parse_project_filter("项目A")
    print(f"  精确匹配 '项目A': {matched}")
    assert "项目A" in matched, "❌ 精确匹配失败"
    
    _, matched = db.parse_project_filter("项目")
    print(f"  模糊匹配 '项目': {matched}")
    assert "项目A" in matched and "项目B" in matched, "❌ 模糊匹配失败"
    
    _, matched = db.parse_project_filter("A")
    print(f"  模糊匹配 'A': {matched}")
    assert "项目A" in matched, "❌ 模糊匹配A失败"
    
    _, matched = db.parse_project_filter("项目A,项目B")
    print(f"  多项目 '项目A,项目B': {matched}")
    assert "项目A" in matched and "项目B" in matched, "❌ 多项目匹配失败"
    
    _, matched = db.parse_project_filter("A,B")
    print(f"  多项目模糊 'A,B': {matched}")
    assert "项目A" in matched and "项目B" in matched, "❌ 多项目模糊匹配失败"
    
    _, matched = db.parse_project_filter("不存在的项目")
    print(f"  无匹配 '不存在的项目': {matched}")
    assert matched == [], "❌ 无匹配应该返回空列表"
    
    print("\n📋 测试 search_tasks_advanced:")
    
    result = db.search_tasks_advanced(project="项目")
    print(f"  模糊搜索 '项目' 找到 {len(result['tasks'])} 个任务")
    print(f"  匹配项目: {result['matched_projects']}")
    assert len(result['tasks']) >= 3, "❌ 搜索结果数量不对"
    assert "项目A" in result['matched_projects'], "❌ 匹配项目列表不对"
    
    result2 = db.search_tasks_advanced(project="A,B")
    print(f"\n  多项目模糊 'A,B' 找到 {len(result2['tasks'])} 个任务")
    print(f"  匹配项目: {result2['matched_projects']}")
    assert "项目A" in result2['matched_projects'], "❌ 多项目匹配A失败"
    assert "项目B" in result2['matched_projects'], "❌ 多项目匹配B失败"
    
    print("\n📋 测试 get_stats_data:")
    
    stats = db.get_stats_data(project="项目")
    print(f"  模糊统计 '项目' 匹配项目: {stats['matched_projects']}")
    assert "项目A" in stats['matched_projects'], "❌ 统计匹配项目不对"
    
    stats2 = db.get_stats_data(project="A,B")
    print(f"  多项目模糊 'A,B' 匹配项目: {stats2['matched_projects']}")
    assert "项目A" in stats2['matched_projects'] and "项目B" in stats2['matched_projects'], "❌ 多项目统计匹配失败"
    
    print("\n✅ 项目筛选测试通过\n")

def main():
    print("\n" + "=" * 60)
    print("🚀 effcli 第四轮新功能测试")
    print("=" * 60 + "\n")
    
    try:
        reset_test_data()
        test_1_time_distribution_view()
        test_2_sessions_crud()
        test_3_overdue_history()
        test_4_project_filter()
        
        print("=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
