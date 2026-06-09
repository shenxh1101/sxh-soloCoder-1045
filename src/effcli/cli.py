import click
import sys
import os
from datetime import datetime, date, timedelta
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .database import Database, Task, Priority, TaskStatus


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

console = Console()
db = Database()


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        return f"{seconds // 60}分钟"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}小时{mins}分钟" if mins > 0 else f"{hours}小时"


def get_priority_color(priority: Priority) -> str:
    return {
        Priority.HIGH: "red",
        Priority.MEDIUM: "yellow",
        Priority.LOW: "green",
    }[priority]


def get_status_color(status: TaskStatus) -> str:
    return {
        TaskStatus.TODO: "white",
        TaskStatus.IN_PROGRESS: "cyan",
        TaskStatus.PAUSED: "magenta",
        TaskStatus.DONE: "green",
        TaskStatus.ARCHIVED: "dim",
    }[status]


def get_status_icon(status: TaskStatus) -> str:
    return {
        TaskStatus.TODO: "◻",
        TaskStatus.IN_PROGRESS: "▶",
        TaskStatus.PAUSED: "⏸",
        TaskStatus.DONE: "✓",
        TaskStatus.ARCHIVED: "📦",
    }[status]


@click.group()
@click.version_option()
def cli():
    """个人效率命令行工具 - 快速管理任务、专注计时、每日回顾"""
    pass


@cli.command()
@click.argument("title", nargs=-1, required=True)
@click.option("-p", "--project", default="default", help="项目名称")
@click.option("-P", "--priority", type=click.Choice(["high", "medium", "low"]), 
              default="medium", help="优先级")
@click.option("-d", "--due", "due_date", help="截止日期 (YYYY-MM-DD)")
def add(title, project, priority, due_date):
    """新增任务"""
    title_str = " ".join(title)
    
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            click.echo(f"错误: 日期格式不正确，请使用 YYYY-MM-DD 格式", err=True)
            return
    
    task = Task(
        title=title_str,
        project=project,
        priority=Priority(priority),
        due_date=due_date,
    )
    
    task_id = db.add_task(task)
    
    task = db.get_task(task_id)
    console.print(Panel(
        f"[bold]任务已创建[/bold]\n\n"
        f"ID: {task.id}\n"
        f"标题: {task.title}\n"
        f"项目: {task.project}\n"
        f"优先级: [{get_priority_color(task.priority)}]{task.priority.value}[/]\n"
        f"截止日期: {task.due_date or '未设置'}",
        title="✓ 成功",
        border_style="green"
    ))


@cli.command("today")
def today_cmd():
    """按项目列出今日事项"""
    tasks = db.get_today_tasks()
    overdue = db.get_overdue_tasks()
    
    if not tasks and not overdue:
        console.print("[dim]今日暂无任务，享受美好的一天吧！[/]")
        return
    
    if overdue:
        table = Table(title=f"⚠️  逾期任务 ({len(overdue)})", box=box.SIMPLE, show_lines=False)
        table.add_column("ID", style="red", no_wrap=True)
        table.add_column("任务", style="red")
        table.add_column("项目", style="dim")
        table.add_column("截止", style="red")
        
        for task in overdue:
            table.add_row(
                str(task.id),
                Text(task.title, style="red"),
                task.project,
                task.due_date
            )
        console.print(table)
        console.print()
    
    grouped = {}
    for task in tasks:
        if task.project not in grouped:
            grouped[task.project] = []
        grouped[task.project].append(task)
    
    for project, project_tasks in sorted(grouped.items()):
        table = Table(title=f"📁 {project}", box=box.SIMPLE, show_lines=False)
        table.add_column("", no_wrap=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("任务")
        table.add_column("优先级", no_wrap=True)
        table.add_column("状态", no_wrap=True)
        table.add_column("专注", style="dim", no_wrap=True)
        table.add_column("截止", style="dim", no_wrap=True)
        
        for task in project_tasks:
            status_icon = get_status_icon(task.status)
            status_color = get_status_color(task.status)
            prio_color = get_priority_color(task.priority)
            focus_time = format_duration(task.total_focus_time) if task.total_focus_time > 0 else "-"
            due_text = task.due_date or "-"
            
            table.add_row(
                f"[{status_color}]{status_icon}[/]",
                str(task.id),
                Text(task.title, style=status_color),
                f"[{prio_color}]{task.priority.value}[/]",
                f"[{status_color}]{task.status.value.replace('_', ' ')}[/]",
                focus_time,
                due_text
            )
        
        console.print(table)
        console.print()


@cli.command()
@click.argument("task_id", type=int)
@click.option("-r", "--reason", help="暂停原因（用于记录中断）")
def start(task_id, reason):
    """启动专注计时，或暂停并记录中断原因"""
    task = db.get_task(task_id)
    
    if not task:
        click.echo(f"错误: 找不到任务 ID {task_id}", err=True)
        return
    
    if reason:
        active_sessions = db.get_active_sessions()
        task_sessions = [s for s in active_sessions if s.task_id == task_id]
        
        if not task_sessions:
            click.echo(f"错误: 任务 {task_id} 没有正在进行的专注会话", err=True)
            return
        
        for session in task_sessions:
            db.pause_focus_session(session.id, reason)
        
        task.status = TaskStatus.PAUSED
        db.update_task(task)
        
        console.print(Panel(
            f"[bold]已暂停专注[/bold]\n\n"
            f"任务: {task.title}\n"
            f"中断原因: {reason}",
            title="⏸ 已暂停",
            border_style="yellow"
        ))
        return
    
    active_sessions = db.get_active_sessions()
    if active_sessions:
        for session in active_sessions:
            db.complete_focus_session(session.id)
            old_task = db.get_task(session.task_id)
            if old_task and old_task.status == TaskStatus.IN_PROGRESS:
                old_task.status = TaskStatus.TODO
                db.update_task(old_task)
    
    db.start_focus_session(task_id)
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.now().isoformat()
    db.update_task(task)
    
    console.print(Panel(
        f"[bold]开始专注！[/bold]\n\n"
        f"任务: {task.title}\n"
        f"项目: {task.project}\n"
        f"优先级: [{get_priority_color(task.priority)}]{task.priority.value}[/]\n\n"
        f"[dim]按 Ctrl+C 或使用 'eff start {task_id} -r \"原因\"' 暂停[/]",
        title="▶ 专注中",
        border_style="cyan"
    ))
    
    try:
        import time
        start_time = datetime.now()
        with console.status("[bold cyan]专注中...[/]", spinner="dots"):
            while True:
                elapsed = int((datetime.now() - start_time).total_seconds())
                console.print(f"\r已专注: {format_duration(elapsed)}", end="")
                time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]检测到中断，请输入中断原因（直接回车忽略）:[/]")
        interrupt_reason = input().strip()
        
        active_sessions = db.get_active_sessions()
        task_sessions = [s for s in active_sessions if s.task_id == task_id]
        
        for session in task_sessions:
            if interrupt_reason:
                db.pause_focus_session(session.id, interrupt_reason)
            else:
                db.complete_focus_session(session.id)
        
        task.status = TaskStatus.PAUSED if interrupt_reason else TaskStatus.TODO
        db.update_task(task)
        
        if interrupt_reason:
            console.print(f"\n[yellow]⏸ 已暂停，原因: {interrupt_reason}[/]")
        else:
            console.print(f"\n[dim]已停止专注[/]")


@cli.command()
@click.argument("task_id", type=int)
@click.option("-s", "--summary", help="完成总结")
def done(task_id, summary):
    """完成任务并写总结"""
    task = db.get_task(task_id)
    
    if not task:
        click.echo(f"错误: 找不到任务 ID {task_id}", err=True)
        return
    
    active_sessions = db.get_active_sessions()
    task_sessions = [s for s in active_sessions if s.task_id == task_id]
    for session in task_sessions:
        db.complete_focus_session(session.id)
    
    if not summary:
        console.print("[cyan]请输入完成总结（直接回车跳过）:[/]")
        summary = input().strip()
    
    task.status = TaskStatus.DONE
    task.completed_at = datetime.now().isoformat()
    task.summary = summary or None
    db.update_task(task)
    
    task = db.get_task(task_id)
    
    console.print(Panel(
        f"[bold]🎉 任务完成！[/bold]\n\n"
        f"任务: {task.title}\n"
        f"项目: {task.project}\n"
        f"总专注时间: {format_duration(task.total_focus_time)}\n"
        f"中断次数: {task.interrupt_count}\n"
        f"总结: {task.summary or '无'}",
        title="✓ 已完成",
        border_style="green"
    ))


@cli.command()
@click.option("-d", "--date", "review_date", help="回顾日期 (YYYY-MM-DD)，默认今天")
@click.option("--report", is_flag=True, help="输出适合粘贴到日报的摘要")
def review(review_date, report):
    """生成每日回顾"""
    if review_date:
        try:
            datetime.strptime(review_date, "%Y-%m-%d")
        except ValueError:
            click.echo(f"错误: 日期格式不正确，请使用 YYYY-MM-DD 格式", err=True)
            return
    else:
        review_date = date.today().isoformat()
    
    data = db.get_daily_review_data(review_date)
    
    if report:
        console.print(f"# 工作日报 - {data['date']}")
        console.print()
        console.print("## 今日完成")
        for task in data['completed']:
            summary = f" - {task.summary}" if task.summary else ""
            archived = " [已归档]" if task.status == TaskStatus.ARCHIVED else ""
            console.print(f"- [{task.project}] {task.title}{summary}{archived}")
        
        if data['started']:
            console.print()
            console.print("## 进行中")
            for task in data['started']:
                console.print(f"- [{task.project}] {task.title}")
        
        if data['overdue']:
            console.print()
            console.print("## ⚠️  逾期未完成")
            for task in data['overdue']:
                console.print(f"- [{task.project}] {task.title} (截止: {task.due_date})")
        
        if data['due_tomorrow']:
            console.print()
            console.print("## 📅 明日到期")
            for task in data['due_tomorrow']:
                prio = f" [{task.priority.value}]" if task.priority != Priority.MEDIUM else ""
                console.print(f"- [{task.project}] {task.title}{prio}")
        
        if data['project_summary']:
            console.print()
            console.print("## 📊 按项目汇总")
            for project, info in sorted(data['project_summary'].items()):
                console.print(f"### {project}")
                console.print(f"- 完成任务: {info['count']} 个")
                console.print(f"- 总专注时长: {format_duration(info['total_focus'])}")
                for task in info['tasks']:
                    summary = f" - {task.summary}" if task.summary else ""
                    console.print(f"  - {task.title}{summary}")
        
        console.print()
        console.print("## 工作统计")
        console.print(f"- 专注时长: {format_duration(data['total_focus_seconds'])}")
        console.print(f"- 专注次数: {data['session_count']}")
        console.print(f"- 中断次数: {data['interruption_count']}")
        console.print(f"- 完成任务: {len(data['completed'])} 个")
        console.print(f"- 新增任务: {len(data['added'])} 个")
        if data['overdue']:
            console.print(f"- 逾期任务: {len(data['overdue'])} 个")
        if data['due_tomorrow']:
            console.print(f"- 明日到期: {len(data['due_tomorrow'])} 个")
        return
    
    console.print(Panel(
        f"[bold]📅 每日回顾 - {data['date']}[/bold]",
        border_style="blue"
    ))
    console.print()
    
    stats = Table(show_header=False, box=None, padding=(0, 2))
    stats.add_row("⏱  总专注时长", f"[bold cyan]{format_duration(data['total_focus_seconds'])}[/]")
    stats.add_row("🔄 专注次数", str(data['session_count']))
    stats.add_row("⚠️  中断次数", f"[yellow]{data['interruption_count']}[/]" if data['interruption_count'] > 0 else "0")
    stats.add_row("✓ 完成任务", f"[green]{len(data['completed'])}[/]")
    stats.add_row("📝 新增任务", str(len(data['added'])))
    stats.add_row("▶ 进行中", str(len(data['started'])))
    if data['overdue']:
        stats.add_row("⚠️  逾期未完成", f"[red]{len(data['overdue'])}[/]")
    if data['due_tomorrow']:
        stats.add_row("📅 明日到期", str(len(data['due_tomorrow'])))
    console.print(stats)
    console.print()
    
    if data['overdue']:
        console.print("[bold red]⚠️  逾期未完成[/]")
        overdue_table = Table(box=box.SIMPLE, show_lines=False)
        overdue_table.add_column("项目", style="dim")
        overdue_table.add_column("任务", style="red")
        overdue_table.add_column("截止日期", style="red")
        overdue_table.add_column("优先级")
        
        for task in data['overdue']:
            prio_color = get_priority_color(task.priority)
            overdue_table.add_row(
                task.project,
                task.title,
                task.due_date,
                f"[{prio_color}]{task.priority.value}[/]"
            )
        console.print(overdue_table)
        console.print()
    
    if data['due_tomorrow']:
        console.print("[bold yellow]📅 明日到期[/]")
        tomorrow_table = Table(box=box.SIMPLE, show_lines=False)
        tomorrow_table.add_column("项目", style="dim")
        tomorrow_table.add_column("任务")
        tomorrow_table.add_column("优先级")
        
        for task in data['due_tomorrow']:
            prio_color = get_priority_color(task.priority)
            tomorrow_table.add_row(
                task.project,
                task.title,
                f"[{prio_color}]{task.priority.value}[/]"
            )
        console.print(tomorrow_table)
        console.print()
    
    if data['completed']:
        console.print("[bold green]✓ 已完成的任务[/]")
        completed_table = Table(box=box.SIMPLE, show_lines=False)
        completed_table.add_column("项目", style="dim")
        completed_table.add_column("任务")
        completed_table.add_column("专注时长", style="dim")
        completed_table.add_column("总结")
        completed_table.add_column("状态", no_wrap=True)
        
        for task in data['completed']:
            status_icon = "📦" if task.status == TaskStatus.ARCHIVED else "✓"
            status_text = "已归档" if task.status == TaskStatus.ARCHIVED else "已完成"
            completed_table.add_row(
                task.project,
                task.title,
                format_duration(task.total_focus_time),
                task.summary or "-",
                f"{status_icon} {status_text}"
            )
        console.print(completed_table)
        console.print()
    
    if data['project_summary']:
        console.print("[bold]📊 按项目汇总[/]")
        project_table = Table(box=box.SIMPLE, show_lines=False)
        project_table.add_column("项目")
        project_table.add_column("完成数", justify="right")
        project_table.add_column("专注时长", justify="right")
        
        for project, info in sorted(data['project_summary'].items()):
            project_table.add_row(
                project,
                str(info['count']),
                format_duration(info['total_focus'])
            )
        console.print(project_table)
        console.print()
    
    if data['started']:
        console.print("[bold cyan]▶ 进行中的任务[/]")
        started_table = Table(box=box.SIMPLE, show_lines=False)
        started_table.add_column("项目", style="dim")
        started_table.add_column("任务")
        started_table.add_column("专注时长", style="dim")
        started_table.add_column("中断次数", style="yellow")
        
        for task in data['started']:
            started_table.add_row(
                task.project,
                task.title,
                format_duration(task.total_focus_time),
                str(task.interrupt_count)
            )
        console.print(started_table)
        console.print()
    
    if data['sessions']:
        console.print("[bold]📊 专注时间线[/]")
        timeline_table = Table(box=box.SIMPLE, show_lines=False)
        timeline_table.add_column("时间", style="dim", no_wrap=True)
        timeline_table.add_column("任务")
        timeline_table.add_column("时长", style="dim", no_wrap=True)
        timeline_table.add_column("状态")
        
        for session in data['sessions']:
            start_time = datetime.fromisoformat(session['start_time']).strftime("%H:%M")
            end_time = datetime.fromisoformat(session['end_time']).strftime("%H:%M") if session['end_time'] else "进行中"
            duration = format_duration(session['duration']) if session['duration'] > 0 else "-"
            
            if session['interrupted']:
                status = f"[yellow]⏸ 中断: {session['interrupt_reason']}[/]"
            else:
                status = "[green]✓ 完成[/]" if session['end_time'] else "[cyan]▶ 进行中[/]"
            
            timeline_table.add_row(
                f"{start_time} - {end_time}",
                session['title'],
                duration,
                status
            )
        console.print(timeline_table)


@cli.command()
def archive():
    """归档已完成事项"""
    count = db.archive_completed_tasks()
    
    if count > 0:
        console.print(Panel(
            f"[bold]已归档 {count} 个已完成的任务[/bold]",
            title="📦 已归档",
            border_style="blue"
        ))
    else:
        console.print("[dim]没有可归档的已完成任务[/]")


@cli.command()
@click.argument("keyword", required=False)
@click.option("-p", "--project", help="按项目筛选")
@click.option("-s", "--status", type=click.Choice(["all", "active", "todo", "in_progress", "paused", "done", "archived"]), help="按状态筛选")
@click.option("--from", "date_from", help="开始日期 (YYYY-MM-DD)")
@click.option("--to", "date_to", help="结束日期 (YYYY-MM-DD)")
def search(keyword, project, status, date_from, date_to):
    """按关键词和条件搜索历史任务"""
    if not keyword and not project and not status and not date_from and not date_to:
        click.echo("错误: 请至少指定一个搜索条件（关键词、项目、状态或日期范围）", err=True)
        return
    
    tasks = db.search_tasks_advanced(
        keyword=keyword,
        project=project,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    
    if not tasks:
        conditions = []
        if keyword:
            conditions.append(f"关键词='{keyword}'")
        if project:
            conditions.append(f"项目='{project}'")
        if status:
            conditions.append(f"状态='{status}'")
        if date_from or date_to:
            date_range = f"{date_from or '...'} - {date_to or '...'}"
            conditions.append(f"日期={date_range}")
        console.print(f"[dim]未找到符合条件的任务: {', '.join(conditions)}[/]")
        return
    
    filters_desc = []
    if keyword:
        filters_desc.append(f"'{keyword}'")
    if project:
        filters_desc.append(f"项目:{project}")
    if status:
        filters_desc.append(f"状态:{status}")
    if date_from or date_to:
        filters_desc.append(f"日期:{date_from or '...'}~{date_to or '...'}")
    
    console.print(f"[bold]找到 {len(tasks)} 个任务[/] ({', '.join(filters_desc)})")
    console.print()
    
    table = Table(box=box.SIMPLE, show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("项目", style="dim")
    table.add_column("任务")
    table.add_column("优先级", no_wrap=True)
    table.add_column("创建日期", style="dim", no_wrap=True)
    table.add_column("完成日期", style="dim", no_wrap=True)
    table.add_column("总结", style="dim")
    
    for task in tasks:
        status_icon = get_status_icon(task.status)
        status_color = get_status_color(task.status)
        prio_color = get_priority_color(task.priority)
        created_date = datetime.fromisoformat(task.created_at).strftime("%Y-%m-%d")
        completed_date = datetime.fromisoformat(task.completed_at).strftime("%Y-%m-%d") if task.completed_at else "-"
        summary = (task.summary[:20] + "...") if task.summary and len(task.summary) > 20 else (task.summary or "-")
        
        table.add_row(
            str(task.id),
            f"[{status_color}]{status_icon} {task.status.value.replace('_', ' ')}[/]",
            task.project,
            task.title,
            f"[{prio_color}]{task.priority.value}[/]",
            created_date,
            completed_date,
            summary
        )
    
    console.print(table)


@cli.command()
@click.argument("task_id", type=int)
def show(task_id):
    """显示任务详情"""
    task = db.get_task(task_id)
    
    if not task:
        click.echo(f"错误: 找不到任务 ID {task_id}", err=True)
        return
    
    created_at = datetime.fromisoformat(task.created_at).strftime("%Y-%m-%d %H:%M")
    started_at = datetime.fromisoformat(task.started_at).strftime("%Y-%m-%d %H:%M") if task.started_at else "-"
    completed_at = datetime.fromisoformat(task.completed_at).strftime("%Y-%m-%d %H:%M") if task.completed_at else "-"
    
    console.print(Panel(
        f"[bold]#{task.id} {task.title}[/bold]\n\n"
        f"项目: {task.project}\n"
        f"优先级: [{get_priority_color(task.priority)}]{task.priority.value}[/]\n"
        f"状态: [{get_status_color(task.status)}]{get_status_icon(task.status)} {task.status.value.replace('_', ' ')}[/]\n"
        f"截止日期: {task.due_date or '未设置'}\n\n"
        f"创建时间: {created_at}\n"
        f"开始时间: {started_at}\n"
        f"完成时间: {completed_at}\n\n"
        f"总专注时间: [cyan]{format_duration(task.total_focus_time)}[/]\n"
        f"中断次数: [yellow]{task.interrupt_count}[/]\n"
        f"中断原因: {task.interrupt_reasons or '-'}\n\n"
        f"总结: {task.summary or '无'}",
        title="📋 任务详情",
        border_style="blue"
    ))


@cli.command()
@click.option("-t", "--task", "task_id", type=int, help="按任务ID筛选")
@click.option("--from", "date_from", help="开始日期 (YYYY-MM-DD)")
@click.option("--to", "date_to", help="结束日期 (YYYY-MM-DD)")
@click.option("-d", "--date", "date", help="指定日期 (YYYY-MM-DD)，等同于 --from 和 --to 同一天")
def sessions(task_id, date_from, date_to, date):
    """查看专注记录历史"""
    if date:
        date_from = date
        date_to = date
    
    sessions_data = db.get_focus_sessions(
        task_id=task_id,
        date_from=date_from,
        date_to=date_to,
    )
    
    if not sessions_data:
        console.print("[dim]没有找到专注记录[/]")
        return
    
    total_duration = sum(s['duration'] for s in sessions_data if s['end_time'])
    total_interrupted = sum(1 for s in sessions_data if s['interrupted'])
    
    filters = []
    if task_id:
        filters.append(f"任务 #{task_id}")
    if date_from or date_to:
        filters.append(f"日期: {date_from or '...'} ~ {date_to or '...'}")
    
    console.print(f"[bold]📊 专注记录[/] ({len(sessions_data)} 条记录, 总时长: {format_duration(total_duration)}, 中断: {total_interrupted} 次)")
    if filters:
        console.print(f"[dim]筛选条件: {', '.join(filters)}[/]")
    console.print()
    
    table = Table(box=box.SIMPLE, show_lines=False)
    table.add_column("日期", style="dim", no_wrap=True)
    table.add_column("时间", style="dim", no_wrap=True)
    table.add_column("任务")
    table.add_column("项目", style="dim")
    table.add_column("时长", no_wrap=True)
    table.add_column("状态")
    table.add_column("中断原因", style="yellow")
    
    for session in sessions_data:
        start_dt = datetime.fromisoformat(session['start_time'])
        date_str = start_dt.strftime("%Y-%m-%d")
        start_time = start_dt.strftime("%H:%M")
        
        if session['end_time']:
            end_dt = datetime.fromisoformat(session['end_time'])
            end_time = end_dt.strftime("%H:%M")
            time_range = f"{start_time} - {end_time}"
            duration = format_duration(session['duration'])
        else:
            time_range = f"{start_time} - 进行中"
            duration = "-"
        
        if session['interrupted']:
            status = "[yellow]⏸ 中断[/]"
            reason = session['interrupt_reason'] or "-"
        elif session['end_time']:
            status = "[green]✓ 完成[/]"
            reason = "-"
        else:
            status = "[cyan]▶ 进行中[/]"
            reason = "-"
        
        table.add_row(
            date_str,
            time_range,
            session['title'],
            session['project'],
            duration,
            status,
            reason
        )
    
    console.print(table)


@cli.command()
@click.argument("task_id", type=int)
@click.option("-t", "--title", help="修改任务标题")
@click.option("-p", "--project", help="修改项目名称")
@click.option("-P", "--priority", type=click.Choice(["high", "medium", "low"]), help="修改优先级")
@click.option("-d", "--due", "due_date", help="修改截止日期 (YYYY-MM-DD)，输入 'none' 清除截止日期")
def edit(task_id, title, project, priority, due_date):
    """修改任务信息"""
    task = db.get_task(task_id)
    
    if not task:
        click.echo(f"错误: 找不到任务 ID {task_id}", err=True)
        return
    
    if not any([title, project, priority, due_date]):
        click.echo("错误: 请至少指定一个要修改的属性（-t, -p, -P, -d）", err=True)
        return
    
    changes = []
    
    if title:
        old_title = task.title
        task.title = title
        changes.append(f"标题: '{old_title}' → '{title}'")
    
    if project:
        old_project = task.project
        task.project = project
        changes.append(f"项目: '{old_project}' → '{project}'")
    
    if priority:
        old_priority = task.priority.value
        task.priority = Priority(priority)
        changes.append(f"优先级: {old_priority} → {priority}")
    
    if due_date:
        if due_date.lower() == "none":
            old_due = task.due_date or "未设置"
            task.due_date = None
            changes.append(f"截止日期: {old_due} → 已清除")
        else:
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
                old_due = task.due_date or "未设置"
                task.due_date = due_date
                changes.append(f"截止日期: {old_due} → {due_date}")
            except ValueError:
                click.echo(f"错误: 日期格式不正确，请使用 YYYY-MM-DD 格式", err=True)
                return
    
    db.update_task(task)
    
    task = db.get_task(task_id)
    
    console.print(Panel(
        f"[bold]任务已更新[/bold]\n\n" + "\n".join(f"- {c}" for c in changes) + "\n\n"
        f"[dim]使用 'eff show {task_id}' 查看完整信息[/]",
        title="✓ 已更新",
        border_style="green"
    ))


@cli.command()
@click.argument("task_id", type=int)
@click.option("-y", "--yes", is_flag=True, help="跳过确认提示")
def delete(task_id, yes):
    """删除任务（包括相关的专注记录）"""
    task = db.get_task(task_id)
    
    if not task:
        click.echo(f"错误: 找不到任务 ID {task_id}", err=True)
        return
    
    if not yes:
        console.print(f"[bold red]警告: 即将删除以下任务及其所有专注记录:[/]")
        console.print(f"  ID: {task.id}")
        console.print(f"  标题: {task.title}")
        console.print(f"  项目: {task.project}")
        console.print(f"  状态: {task.status.value}")
        console.print(f"  专注时长: {format_duration(task.total_focus_time)}")
        console.print()
        confirm = input("确认删除? (y/N): ").strip().lower()
        if confirm != 'y':
            console.print("[dim]已取消删除[/]")
            return
    
    success = db.delete_task(task_id)
    
    if success:
        console.print(Panel(
            f"[bold]任务已删除[/bold]\n\n"
            f"ID: {task.id}\n"
            f"标题: {task.title}",
            title="✓ 已删除",
            border_style="red"
        ))
    else:
        click.echo(f"错误: 删除任务失败", err=True)


if __name__ == "__main__":
    cli()
