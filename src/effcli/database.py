import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    DONE = "done"
    ARCHIVED = "archived"


@dataclass
class Task:
    id: Optional[int] = None
    title: str = ""
    project: str = "default"
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    due_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: Optional[str] = None
    total_focus_time: int = 0
    interrupt_count: int = 0
    interrupt_reasons: str = ""


@dataclass
class FocusSession:
    id: Optional[int] = None
    task_id: int = 0
    start_time: str = ""
    end_time: Optional[str] = None
    duration: int = 0
    interrupted: bool = False
    interrupt_reason: Optional[str] = None


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.environ.get("EFFCLI_DB_PATH")
            if db_path is None:
                home = os.path.expanduser("~")
                eff_dir = os.path.join(home, ".effcli")
                try:
                    os.makedirs(eff_dir, exist_ok=True)
                    db_path = os.path.join(eff_dir, "effcli.db")
                except (PermissionError, OSError):
                    cwd = os.getcwd()
                    eff_dir = os.path.join(cwd, ".effcli")
                    os.makedirs(eff_dir, exist_ok=True)
                    db_path = os.path.join(eff_dir, "effcli.db")
        
        self.db_path = db_path
        self._init_db()
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    project TEXT NOT NULL DEFAULT 'default',
                    priority TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'todo',
                    due_date TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    summary TEXT,
                    total_focus_time INTEGER DEFAULT 0,
                    interrupt_count INTEGER DEFAULT 0,
                    interrupt_reasons TEXT DEFAULT ''
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration INTEGER DEFAULT 0,
                    interrupted BOOLEAN DEFAULT 0,
                    interrupt_reason TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            """)
            
            conn.commit()
    
    def add_task(self, task: Task) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO tasks (title, project, priority, status, due_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task.title, task.project, task.priority.value, task.status.value,
                  task.due_date, task.created_at))
            conn.commit()
            return cursor.lastrowid
    
    def get_task(self, task_id: int) -> Optional[Task]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._row_to_task(row) if row else None
    
    def update_task(self, task: Task) -> None:
        with self._connect() as conn:
            conn.execute("""
                UPDATE tasks SET 
                    title=?, project=?, priority=?, status=?, due_date=?,
                    started_at=?, completed_at=?, summary=?, 
                    total_focus_time=?, interrupt_count=?, interrupt_reasons=?
                WHERE id=?
            """, (task.title, task.project, task.priority.value, task.status.value,
                  task.due_date, task.started_at, task.completed_at, task.summary,
                  task.total_focus_time, task.interrupt_count, task.interrupt_reasons,
                  task.id))
            conn.commit()
    
    def get_today_tasks(self) -> List[Task]:
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks 
                WHERE status != 'archived'
                AND (DATE(created_at) = ? OR DATE(due_date) = ? OR status IN ('todo', 'in_progress', 'paused'))
                ORDER BY 
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    project, created_at
            """, (today, today)).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def get_active_sessions(self) -> List[FocusSession]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM focus_sessions WHERE end_time IS NULL
            """).fetchall()
            return [self._row_to_session(row) for row in rows]
    
    def start_focus_session(self, task_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO focus_sessions (task_id, start_time)
                VALUES (?, ?)
            """, (task_id, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid
    
    def pause_focus_session(self, session_id: int, interrupt_reason: Optional[str] = None) -> None:
        with self._connect() as conn:
            session = conn.execute("""
                SELECT * FROM focus_sessions WHERE id = ?
            """, (session_id,)).fetchone()
            
            if session:
                start_time = datetime.fromisoformat(session['start_time'])
                end_time = datetime.now()
                duration = int((end_time - start_time).total_seconds())
                
                conn.execute("""
                    UPDATE focus_sessions 
                    SET end_time=?, duration=?, interrupted=?, interrupt_reason=?
                    WHERE id=?
                """, (end_time.isoformat(), duration, 
                      interrupt_reason is not None, interrupt_reason, session_id))
                
                conn.execute("""
                    UPDATE tasks 
                    SET total_focus_time = total_focus_time + ?,
                        interrupt_count = interrupt_count + ?,
                        interrupt_reasons = CASE WHEN interrupt_reasons = '' THEN ? ELSE interrupt_reasons || '; ' || ? END
                    WHERE id = ?
                """, (duration, 1 if interrupt_reason else 0, 
                      interrupt_reason or "", interrupt_reason or "", 
                      session['task_id']))
                
                conn.commit()
    
    def complete_focus_session(self, session_id: int) -> None:
        with self._connect() as conn:
            session = conn.execute("""
                SELECT * FROM focus_sessions WHERE id = ?
            """, (session_id,)).fetchone()
            
            if session:
                start_time = datetime.fromisoformat(session['start_time'])
                end_time = datetime.now()
                duration = int((end_time - start_time).total_seconds())
                
                conn.execute("""
                    UPDATE focus_sessions 
                    SET end_time=?, duration=?, interrupted=0
                    WHERE id=?
                """, (end_time.isoformat(), duration, session_id))
                
                conn.execute("""
                    UPDATE tasks 
                    SET total_focus_time = total_focus_time + ?
                    WHERE id = ?
                """, (duration, session['task_id']))
                
                conn.commit()
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks WHERE status = ?
                ORDER BY created_at DESC
            """, (status.value,)).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def search_tasks(self, keyword: str) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks 
                WHERE title LIKE ? OR summary LIKE ? OR interrupt_reasons LIKE ?
                ORDER BY created_at DESC
            """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def get_all_projects(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT DISTINCT project FROM tasks WHERE project != 'default'
                ORDER BY project
            """).fetchall()
            return [row['project'] for row in rows]
    
    def archive_completed_tasks(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'archived' 
                WHERE status = 'done'
            """)
            conn.commit()
            return cursor.rowcount
    
    def get_overdue_tasks(self) -> List[Task]:
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks 
                WHERE status NOT IN ('done', 'archived')
                AND due_date IS NOT NULL 
                AND DATE(due_date) < ?
                ORDER BY due_date
            """, (today,)).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def get_daily_review_data(self, review_date: Optional[str] = None) -> Dict[str, Any]:
        if review_date is None:
            review_date = date.today().isoformat()
        
        next_day = (datetime.fromisoformat(review_date) + timedelta(days=1)).date().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        
        with self._connect() as conn:
            completed = conn.execute("""
                SELECT * FROM tasks 
                WHERE (status = 'done' OR status = 'archived') 
                AND DATE(completed_at) = ?
                ORDER BY project, completed_at
            """, (review_date,)).fetchall()
            
            started = conn.execute("""
                SELECT * FROM tasks 
                WHERE status IN ('in_progress', 'paused') 
                AND DATE(started_at) = ?
                ORDER BY project, started_at
            """, (review_date,)).fetchall()
            
            added = conn.execute("""
                SELECT * FROM tasks 
                WHERE DATE(created_at) = ?
                ORDER BY project, created_at
            """, (review_date,)).fetchall()
            
            sessions = conn.execute("""
                SELECT fs.*, t.title, t.project 
                FROM focus_sessions fs
                JOIN tasks t ON fs.task_id = t.id
                WHERE DATE(fs.start_time) = ?
                ORDER BY fs.start_time
            """, (review_date,)).fetchall()
            
            overdue = conn.execute("""
                SELECT * FROM tasks 
                WHERE status NOT IN ('done', 'archived')
                AND due_date IS NOT NULL 
                AND DATE(due_date) < ?
                ORDER BY due_date
            """, (review_date,)).fetchall()
            
            due_tomorrow = conn.execute("""
                SELECT * FROM tasks 
                WHERE status NOT IN ('done', 'archived')
                AND due_date IS NOT NULL 
                AND DATE(due_date) = ?
                ORDER BY project, priority
            """, (tomorrow,)).fetchall()
            
            total_focus = sum(s['duration'] for s in sessions if s['end_time'])
            
            project_summary = {}
            for row in completed:
                task = self._row_to_task(row)
                if task.project not in project_summary:
                    project_summary[task.project] = {
                        'count': 0,
                        'total_focus': 0,
                        'tasks': []
                    }
                project_summary[task.project]['count'] += 1
                project_summary[task.project]['total_focus'] += task.total_focus_time
                project_summary[task.project]['tasks'].append(task)
            
            return {
                'date': review_date,
                'completed': [self._row_to_task(r) for r in completed],
                'started': [self._row_to_task(r) for r in started],
                'added': [self._row_to_task(r) for r in added],
                'sessions': sessions,
                'overdue': [self._row_to_task(r) for r in overdue],
                'due_tomorrow': [self._row_to_task(r) for r in due_tomorrow],
                'project_summary': project_summary,
                'total_focus_seconds': total_focus,
                'session_count': len(sessions),
                'interruption_count': sum(1 for s in sessions if s['interrupted']),
            }
    
    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row['id'],
            title=row['title'],
            project=row['project'],
            priority=Priority(row['priority']),
            status=TaskStatus(row['status']),
            due_date=row['due_date'],
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            summary=row['summary'],
            total_focus_time=row['total_focus_time'],
            interrupt_count=row['interrupt_count'],
            interrupt_reasons=row['interrupt_reasons'] or "",
        )
    
    def _row_to_session(self, row: sqlite3.Row) -> FocusSession:
        return FocusSession(
            id=row['id'],
            task_id=row['task_id'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            duration=row['duration'],
            interrupted=bool(row['interrupted']),
            interrupt_reason=row['interrupt_reason'],
        )
    
    def search_tasks_advanced(
        self, 
        keyword: Optional[str] = None,
        project: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Task]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if keyword:
            query += " AND (title LIKE ? OR summary LIKE ? OR interrupt_reasons LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
        
        if project:
            query += " AND project = ?"
            params.append(project)
        
        if status:
            if status == "all":
                pass
            elif status == "active":
                query += " AND status IN ('todo', 'in_progress', 'paused')"
            else:
                query += " AND status = ?"
                params.append(status)
        
        if date_from:
            query += " AND DATE(created_at) >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(created_at) <= ?"
            params.append(date_to)
        
        query += " ORDER BY created_at DESC"
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_task(row) for row in rows]
    
    def get_focus_sessions(
        self,
        task_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT fs.*, t.title, t.project 
            FROM focus_sessions fs
            JOIN tasks t ON fs.task_id = t.id
            WHERE 1=1
        """
        params = []
        
        if task_id:
            query += " AND fs.task_id = ?"
            params.append(task_id)
        
        if date_from:
            query += " AND DATE(fs.start_time) >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(fs.start_time) <= ?"
            params.append(date_to)
        
        query += " ORDER BY fs.start_time DESC"
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def delete_task(self, task_id: int) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM focus_sessions WHERE task_id = ?", (task_id,))
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_tasks(self) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks 
                ORDER BY 
                    CASE status 
                        WHEN 'todo' THEN 1 
                        WHEN 'in_progress' THEN 2 
                        WHEN 'paused' THEN 3
                        WHEN 'done' THEN 4
                        ELSE 5 
                    END,
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    created_at DESC
            """).fetchall()
            return [self._row_to_task(row) for row in rows]
