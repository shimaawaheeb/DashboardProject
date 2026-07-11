const state = {
  data: null,
  page: "overview",
  department: "All",
  user: null,
  pendingPage: null,
  pendingAssistant: false,
  resetToken: null,
  signupOtpEmail: null,
  selectedAvatar: "avatar-executive",
  selectedSettingsAvatar: "avatar-executive",
  adminTable: "Employees",
  adminSearch: "",
  adminEditingRecord: null,
  adminUsers: [],
  adminRequiredFields: {},
  adminUndoStack: [],
  adminRedoStack: []
};
const avatars = [
  ["avatar-finance", "Finance"],
  ["avatar-it", "Information Technology"],
  ["avatar-cyber", "Cybersecurity"],
  ["avatar-data", "Data & Analytics"],
  ["avatar-marketing", "Marketing"],
  ["avatar-customer", "Customer Experience"],
  ["avatar-legal", "Legal & Compliance"],
  ["avatar-procurement", "Procurement"],
  ["avatar-hr", "Human Resources"],
  ["avatar-operations", "Operations"],
  ["avatar-training", "Corporate Training"],
  ["avatar-executive", "Executive Office"]
];
const protectedPages = new Set(["delivery", "workforce", "governance", "assistant", "settings", "my-dashboard", "admin"]);
const colors = {
  teal: "#087e8b", green: "#27845b", amber: "#c27b17",
  red: "#c34646", blue: "#3f6f9d", gray: "#9aa8b2", navy: "#102a43"
};
const pageInfo = {
  overview: ["Portfolio overview", "Executive view of delivery, investment, and portfolio health."],
  delivery: ["Project delivery", "Execution health, deadlines, blockers, and workload pressure."],
  workforce: ["Workforce", "Roster composition, capacity coverage, and assignment distribution."],
  governance: ["Governance & activity", "Weekly health, meeting outcomes, and operational engagement."],
  settings: ["Settings", "Manage your account profile, avatar, and password."],
  "my-dashboard": ["My dashboard", "Your employee profile, projects, tasks, deadlines, and meetings."],
  admin: ["Admin", "Manage workbook data and admin access."]
};

const n = value => Number(value || 0);
const sum = (rows, field) => rows.reduce((total, row) => total + n(row[field]), 0);
const pct = (part, total, digits = 1) => total ? `${(part / total * 100).toFixed(digits)}%` : "—";
const money = value => new Intl.NumberFormat("en-SA", { style: "currency", currency: "SAR", notation: "compact", maximumFractionDigits: 2 }).format(value);
const integer = value => new Intl.NumberFormat("en-US").format(Math.round(value || 0));
const shortDate = value => value ? new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)) : "—";
const dateTime = value => value ? new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "—";
const group = (rows, field) => rows.reduce((result, row) => {
  const key = row[field] ?? "Unknown"; result[key] = (result[key] || 0) + 1; return result;
}, {});
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
const statusClass = value => ["At Risk", "Blocked", "Red", "High", "Critical"].includes(value) ? "red"
  : ["Planning", "On Hold", "Amber", "Medium", "In Review"].includes(value) ? "amber"
  : ["Completed", "Green", "Active", "Low"].includes(value) ? "green" : "blue";
const badge = value => `<span class="badge ${statusClass(value)}">${escapeHtml(value)}</span>`;
const card = (title, subtitle, body, extra = "") => `<article class="card ${extra}"><div class="card-header"><div><h2>${title}</h2><p>${subtitle}</p></div></div>${body}</article>`;
const kpi = (label, value, meta, color = colors.teal) => `<article class="card kpi" style="--accent:${color}"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div><div class="kpi-meta">${meta}</div></article>`;
const bars = (entries, formatter = integer, color = colors.teal) => {
  const max = Math.max(...entries.map(([, value]) => value), 1);
  return `<div class="bar-list">${entries.map(([label, value], index) =>
    `<div class="bar-row"><span class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</span><div class="bar-track"><div class="bar-fill" style="width:${value / max * 100}%;--bar:${Array.isArray(color) ? color[index % color.length] : color}"></div></div><span class="bar-value">${formatter(value)}</span></div>`
  ).join("")}</div>`;
};
const donut = (segments, center, label) => {
  const total = segments.reduce((a, [, v]) => a + v, 0) || 1;
  let angle = 0;
  const stops = segments.map(([name, value, color]) => {
    const start = angle; angle += value / total * 360;
    return `${color} ${start}deg ${angle}deg`;
  }).join(",");
  return `<div class="donut-wrap"><div class="donut" style="background:conic-gradient(${stops})"><div class="donut-center"><b>${center}</b><span>${label}</span></div></div><div class="legend">${segments.map(([name, value, color]) => `<span><i style="background:${color}"></i>${escapeHtml(name)} ${value}</span>`).join("")}</div></div>`;
};
const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;

function filteredTables() {
  const source = state.data.tables;
  if (state.department === "All") return source;
  const department = state.department;
  const projects = source.Projects.filter(row => row.Department === department);
  const projectIds = new Set(projects.map(row => row["Project ID"]));
  return {
    ...source,
    Departments: source.Departments.filter(row => row["Department Name"] === department),
    Employees: source.Employees.filter(row => row.Department === department),
    Projects: projects,
    Tasks: source.Tasks.filter(row => projectIds.has(row["Project ID"])),
    Meetings: source.Meetings.filter(row => projectIds.has(row["Project ID"])),
    "Weekly Updates": source["Weekly Updates"].filter(row => projectIds.has(row["Project ID"])),
    "Activity Log": source["Activity Log"].filter(row => projectIds.has(row["Project ID"]))
  };
}

function portfolioOverview(d) {
  const projects = d.Projects, tasks = d.Tasks;
  const open = projects.filter(row => row.Status !== "Completed");
  const completed = projects.filter(row => row.Status === "Completed");
  const budget = sum(projects, "Budget SAR"), spend = sum(projects, "Actual Spend SAR");
  const status = group(projects, "Status");
  const today = new Date();
  const overdueProjects = open.filter(row => new Date(row["Target End Date"]) < today);
  const openTasks = tasks.filter(row => row.Status !== "Completed");
  const blocked = tasks.filter(row => row.Status === "Blocked");
  const latest = {};
  d["Weekly Updates"].forEach(row => {
    if (!latest[row["Project ID"]] || row["Week Starting"] > latest[row["Project ID"]]["Week Starting"]) latest[row["Project ID"]] = row;
  });
  const health = group(Object.values(latest), "Health");
  const riskRows = open.map(project => {
    const projectTasks = tasks.filter(task => task["Project ID"] === project["Project ID"]);
    const overdue = projectTasks.filter(task => task.Status !== "Completed" && new Date(task["Due Date"]) < today).length;
    const spendRate = n(project["Actual Spend SAR"]) / n(project["Budget SAR"]) * 100;
    return { ...project, overdue, spendRate, score: (project.Status === "At Risk" ? 4 : 0) + (project["Risk Level"] === "High" ? 3 : 0) + overdue / 5 + Math.max(0, spendRate - n(project["Progress %"])) / 10 };
  }).sort((a, b) => b.score - a.score).slice(0, 8);
  const departmentBudgets = Object.entries(projects.reduce((a, row) => {
    a[row.Department] = (a[row.Department] || 0) + n(row["Budget SAR"]); return a;
  }, {})).sort((a, b) => b[1] - a[1]).slice(0, 7);

  return `
    <section class="grid kpi-grid">
      ${kpi("Total projects", integer(projects.length), `<strong>${open.length}</strong> currently open`)}
      ${kpi("At-risk projects", integer(status["At Risk"] || 0), `${pct(status["At Risk"] || 0, projects.length)} of portfolio`, colors.red)}
      ${kpi("Portfolio budget", money(budget), `${money(spend)} actual spend`, colors.blue)}
      ${kpi("Budget utilization", pct(spend, budget), `${money(budget - spend)} remaining`, colors.amber)}
      ${kpi("Open tasks", integer(openTasks.length), `<strong>${blocked.length}</strong> blocked`, blocked.length ? colors.red : colors.green)}
    </section>
    <section class="grid two-col">
      ${card("Portfolio status", "Current status from the project master", `<div class="card-body">${donut([
        ["In progress", status["In Progress"] || 0, colors.teal], ["At risk", status["At Risk"] || 0, colors.red],
        ["Completed", status.Completed || 0, colors.green], ["Planning", status.Planning || 0, colors.blue],
        ["On hold", status["On Hold"] || 0, colors.amber], ["Not started", status["Not Started"] || 0, colors.gray]
      ], projects.length, "Projects")}</div>`)}
      ${card("Latest reported health", "Latest weekly update for each project", `<div class="card-body">${donut([
        ["Green", health.Green || 0, colors.green], ["Amber", health.Amber || 0, colors.amber], ["Red", health.Red || 0, colors.red]
      ], Object.keys(latest).length, "Updates")}</div>`)}
    </section>
    <section class="grid two-col">
      ${card("Investment by department", "Approved project budget", `<div class="card-body">${bars(departmentBudgets, money, colors.blue)}</div>`)}
      ${card("Management attention", "Current exceptions requiring review", `<div class="card-body insight-list">
        <div class="insight"><div class="insight-icon">!</div><p>${overdueProjects.length} open projects past target date<span>Schedule exception based on today</span></p></div>
        <div class="insight"><div class="insight-icon">↗</div><p>${open.filter(p => n(p["Actual Spend SAR"]) / n(p["Budget SAR"]) > n(p["Progress %"]) / 100).length} open projects with spend ahead of progress<span>Review burn rate and delivery plan</span></p></div>
        <div class="insight"><div class="insight-icon">×</div><p>${blocked.length} blocked tasks across ${new Set(blocked.map(t => t["Project ID"])).size} projects<span>Prioritize blocker resolution</span></p></div>
      </div>`)}
    </section>
    ${card("Projects requiring attention", "Ranked using status, risk, overdue tasks, and spend-to-progress pressure", table(
      ["Project", "Status", "Risk", "Progress", "Spend", "Overdue tasks"],
      riskRows.map(row => `<tr><td class="project-name">${escapeHtml(row["Project Name"])}<span class="subtext">${escapeHtml(row.Department)}</span></td><td>${badge(row.Status)}</td><td>${badge(row["Risk Level"])}</td><td><b>${row["Progress %"]}%</b><div class="progress-track" style="width:90px;margin-top:5px"><div class="progress-fill" style="width:${row["Progress %"]}%"></div></div></td><td>${row.spendRate.toFixed(1)}%</td><td>${row.overdue}</td></tr>`)
    ))}
  `;
}

function deliveryPage(d) {
  const tasks = d.Tasks, projects = d.Projects, today = new Date();
  const open = tasks.filter(row => row.Status !== "Completed");
  const completed = tasks.filter(row => row.Status === "Completed");
  const blocked = tasks.filter(row => row.Status === "Blocked");
  const overdue = open.filter(row => new Date(row["Due Date"]) < today);
  const critical = open.filter(row => row.Priority === "Critical");
  const known = tasks.filter(row => row["Actual Hours"] !== null);
  const status = Object.entries(group(tasks, "Status")).sort((a, b) => b[1] - a[1]);
  const overdueDept = Object.entries(group(overdue, "Department")).sort((a,b) => b[1]-a[1]).slice(0,8);
  const employeeMap = Object.fromEntries(d.Employees.map(e => [e["Employee ID"], e]));
  const workload = Object.entries(group(open, "Assigned To ID")).map(([id, value]) => [employeeMap[id]?.["Employee Name"] || id, value]).sort((a,b) => b[1]-a[1]).slice(0,8);
  const projectRows = projects.map(project => {
    const related = tasks.filter(task => task["Project ID"] === project["Project ID"]);
    return { ...project, total: related.length, open: related.filter(t => t.Status !== "Completed").length, overdue: related.filter(t => t.Status !== "Completed" && new Date(t["Due Date"]) < today).length, blocked: related.filter(t => t.Status === "Blocked").length };
  }).sort((a,b) => b.overdue-a.overdue);
  return `
    <section class="grid kpi-grid">
      ${kpi("Total tasks", integer(tasks.length), `${integer(open.length)} open`)}
      ${kpi("Completion rate", pct(completed.length, tasks.length), `${completed.length} completed`, colors.green)}
      ${kpi("Overdue open", integer(overdue.length), `${pct(overdue.length, open.length)} of open tasks`, colors.red)}
      ${kpi("Blocked", integer(blocked.length), `${pct(blocked.length, open.length)} blocked rate`, colors.red)}
      ${kpi("Critical open", integer(critical.length), "Immediate priority", colors.amber)}
    </section>
    <section class="grid equal-col">
      ${card("Task status", "Current execution pipeline", `<div class="card-body">${bars(status, integer, [colors.teal, colors.blue, colors.green, colors.amber, colors.gray, colors.red])}</div>`)}
      ${card("Effort control", "Actual-hour comparison uses tasks with recorded hours only", `<div class="card-body">
        <div class="metric-pair"><span>Estimated hours—all tasks</span><b>${integer(sum(tasks, "Estimated Hours"))}</b></div>
        <div class="metric-pair"><span>Recorded actual hours</span><b>${integer(sum(known, "Actual Hours"))}</b></div>
        <div class="metric-pair"><span>Actual-hour coverage</span><b>${pct(known.length, tasks.length)}</b></div>
        <div class="metric-pair"><span>Variance on comparable tasks</span><b>${integer(sum(known, "Actual Hours") - sum(known, "Estimated Hours"))} h</b></div>
      </div>`)}
    </section>
    <section class="grid equal-col">
      ${card("Overdue tasks by assignee department", "Excludes completed tasks", `<div class="card-body">${bars(overdueDept, integer, colors.red)}</div>`)}
      ${card("Highest open workloads", "Task count per assigned employee", `<div class="card-body">${bars(workload, integer, colors.amber)}</div>`)}
    </section>
    ${card("Project delivery detail", "Task execution grouped by project", table(
      ["Project", "Project status", "Total tasks", "Open", "Overdue", "Blocked", "Progress"],
      projectRows.map(row => `<tr><td class="project-name">${escapeHtml(row["Project Name"])}<span class="subtext">${escapeHtml(row.Department)}</span></td><td>${badge(row.Status)}</td><td>${row.total}</td><td>${row.open}</td><td>${row.overdue ? `<b style="color:${colors.red}">${row.overdue}</b>` : "0"}</td><td>${row.blocked}</td><td>${row["Progress %"]}%</td></tr>`)
    ))}
  `;
}

function workforcePage(d) {
  const employees = d.Employees, departments = d.Departments;
  const tasks = state.department === "All"
    ? state.data.tables.Tasks
    : state.data.tables.Tasks.filter(row => row.Department === state.department);
  const status = group(employees, "Employment Status"), levels = Object.entries(group(employees, "Level")).sort((a,b)=>b[1]-a[1]);
  const locations = Object.entries(group(employees, "Location")).sort((a,b)=>b[1]-a[1]);
  const assigned = new Set(tasks.map(row => row["Assigned To ID"]));
  const orgHeadcount = sum(departments, "Headcount");
  const deptRows = departments.map(dept => {
    const roster = employees.filter(e => e["Department ID"] === dept["Department ID"]);
    const deptTasks = tasks.filter(t => t["Department ID"] === dept["Department ID"] && t.Status !== "Completed");
    return { ...dept, roster: roster.length, active: roster.filter(e => e["Employment Status"] === "Active").length, open: deptTasks.length, hours: sum(deptTasks, "Estimated Hours") };
  }).sort((a,b)=>b.roster-a.roster);
  return `
    <section class="grid kpi-grid">
      ${kpi("Employee records", integer(employees.length), `${integer(status.Active || 0)} active`)}
      ${kpi("Active rate", pct(status.Active || 0, employees.length), `${status["On Leave"] || 0} on leave`, colors.green)}
      ${kpi("Reported headcount", integer(orgHeadcount), "Department capacity measure", colors.blue)}
      ${kpi("Roster coverage", pct(employees.length, orgHeadcount), "Detailed records ÷ headcount", colors.amber)}
      ${kpi("Assigned employees", integer([...assigned].filter(id => employees.some(e => e["Employee ID"] === id)).length), "At least one task")}
    </section>
    <section class="grid three-col">
      ${card("Employment status", "Detailed employee records", `<div class="card-body">${donut([
        ["Active", status.Active || 0, colors.green], ["Contractor", status.Contractor || 0, colors.blue], ["On leave", status["On Leave"] || 0, colors.amber]
      ], employees.length, "Employees")}</div>`)}
      ${card("Seniority mix", "Employees by organizational level", `<div class="card-body">${bars(levels, integer, colors.teal)}</div>`)}
      ${card("Work locations", "Employee record distribution", `<div class="card-body">${bars(locations, integer, colors.blue)}</div>`)}
    </section>
    ${card("Department capacity and workload", "Headcount and roster are intentionally shown as separate measures", table(
      ["Department", "Division", "Reported headcount", "Roster records", "Active", "Open tasks", "Est. open hours"],
      deptRows.map(row => `<tr><td class="project-name">${escapeHtml(row["Department Name"])}<span class="subtext">${escapeHtml(row.Location)}</span></td><td>${escapeHtml(row.Division)}</td><td>${integer(row.Headcount)}</td><td>${row.roster}</td><td>${row.active}</td><td>${row.open}</td><td>${integer(row.hours)}</td></tr>`)
    ))}
  `;
}

function governancePage(d) {
  const updates = d["Weekly Updates"], meetings = d.Meetings, activities = d["Activity Log"];
  const latest = {};
  updates.forEach(row => { if (!latest[row["Project ID"]] || row["Week Starting"] > latest[row["Project ID"]]["Week Starting"]) latest[row["Project ID"]] = row; });
  const health = group(Object.values(latest), "Health");
  const outcomes = Object.entries(group(meetings, "Outcome")).sort((a,b)=>b[1]-a[1]);
  const sources = Object.entries(group(activities, "Source")).sort((a,b)=>b[1]-a[1]);
  const types = Object.entries(group(activities, "Activity Type")).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const weekActivity = {};
  activities.forEach(row => {
    const dt = new Date(row.Timestamp); const start = new Date(dt); start.setDate(dt.getDate() - dt.getDay()); const key = start.toISOString().slice(0,10);
    weekActivity[key] = (weekActivity[key] || 0) + 1;
  });
  const weekly = Object.entries(weekActivity).sort().slice(-7), max = Math.max(...weekly.map(([,v])=>v),1);
  const latestRows = Object.values(latest).sort((a,b) => ({Red:0,Amber:1,Green:2}[a.Health]-({Red:0,Amber:1,Green:2}[b.Health])));
  return `
    <section class="grid kpi-grid">
      ${kpi("Latest green health", integer(health.Green || 0), `${pct(health.Green || 0, Object.keys(latest).length)} of reported projects`, colors.green)}
      ${kpi("Latest amber / red", integer((health.Amber || 0)+(health.Red || 0)), "Requires monitoring", colors.amber)}
      ${kpi("Meetings", integer(meetings.length), `${(sum(meetings, "Duration Minutes")/60).toFixed(1)} total hours`, colors.blue)}
      ${kpi("Follow-up required", integer(meetings.filter(m=>m.Outcome==="Follow-up required").length), `${meetings.filter(m=>m.Outcome==="Blocked pending approval").length} approval blocks`, colors.red)}
      ${kpi("Activity events", integer(activities.length), `${activities.filter(a=>a.Impact==="High").length} high impact`)}
    </section>
    <section class="grid equal-col">
      ${card("Meeting outcomes", "Governance effectiveness indicators", `<div class="card-body">${bars(outcomes, integer, [colors.teal, colors.green, colors.amber, colors.blue, colors.red])}</div>`)}
      ${card("Activity by source", "Operational channel adoption", `<div class="card-body">${bars(sources, integer, colors.blue)}</div>`)}
    </section>
    <section class="grid equal-col">
      ${card("Recent activity trend", "Last seven active weeks", `<div class="card-body"><div class="heat-list">${weekly.map(([date,value])=>`<div class="heat-column"><div class="heat-bar" style="height:${value/max*120}px"></div><span>${date.slice(5)}</span></div>`).join("")}</div></div>`)}
      ${card("Most frequent activity", "Event volume indicates engagement, not productivity", `<div class="card-body">${bars(types, integer, colors.teal)}</div>`)}
    </section>
    ${card("Latest weekly project update", "Latest reported health, blocker, and next action per project", table(
      ["Project", "Week", "Health", "Reported status", "Progress", "Blocker / risk", "Next step"],
      latestRows.map(row=>`<tr><td class="project-name">${escapeHtml(row.Project)}<span class="subtext">${escapeHtml(row.Department)}</span></td><td>${shortDate(row["Week Starting"])}</td><td>${badge(row.Health)}</td><td>${badge(row.Status)}</td><td>${row["Progress %"]}%</td><td>${escapeHtml(row["Blocker/Risk"])}</td><td>${escapeHtml(row["Next Step"])}</td></tr>`)
    ))}
  `;
}

function currentEmployee() {
  const email = (state.user?.email || "").trim().toLowerCase();
  if (!email || !state.data?.tables?.Employees) return null;
  return state.data.tables.Employees.find(row => String(row.Email || "").trim().toLowerCase() === email) || null;
}

function myDashboardPage() {
  const employee = currentEmployee();
  if (!employee) {
    return card("Employee record not found", "Your account is active, but no matching employee row was found in the cleaned workbook.", `
      <div class="card-body insight-list">
        <div class="insight"><div class="insight-icon">!</div><p>No employee record matches ${escapeHtml(state.user?.email || "your account email")}<span>Refresh the workbook or confirm the account email exists in the Employees sheet.</span></p></div>
      </div>
    `);
  }

  const tables = state.data.tables;
  const today = new Date();
  const employeeId = employee["Employee ID"];
  const ownedProjects = tables.Projects.filter(row => row["Owner ID"] === employeeId);
  const assignedTasks = tables.Tasks.filter(row => row["Assigned To ID"] === employeeId);
  const assignedProjectIds = new Set(assignedTasks.map(row => row["Project ID"]));
  const employeeProjects = tables.Projects.filter(row =>
    row["Owner ID"] === employeeId || assignedProjectIds.has(row["Project ID"])
  );
  const employeeProjectIds = new Set(employeeProjects.map(row => row["Project ID"]));
  const openTasks = assignedTasks.filter(row => row.Status !== "Completed");
  const overdueTasks = openTasks.filter(row => new Date(row["Due Date"]) < today);
  const upcomingMeetings = tables.Meetings
    .filter(row => (row["Organizer ID"] === employeeId || employeeProjectIds.has(row["Project ID"])) && new Date(row["Date/Time"]) >= today)
    .sort((a, b) => new Date(a["Date/Time"]) - new Date(b["Date/Time"]))
    .slice(0, 8);
  const recentActivity = tables["Activity Log"]
    .filter(row => row["Employee ID"] === employeeId || employeeProjectIds.has(row["Project ID"]))
    .sort((a, b) => new Date(b.Timestamp) - new Date(a.Timestamp))
    .slice(0, 8);

  const projectRows = employeeProjects
    .sort((a, b) => new Date(a["Target End Date"]) - new Date(b["Target End Date"]))
    .map(row => `<tr><td class="project-name">${escapeHtml(row["Project Name"])}<span class="subtext">${row["Owner ID"] === employeeId ? "Owner" : "Assigned through tasks"}</span></td><td>${badge(row.Status)}</td><td>${badge(row["Risk Level"])}</td><td>${row["Progress %"]}%</td><td>${shortDate(row["Target End Date"])}</td></tr>`);
  const taskRows = assignedTasks
    .sort((a, b) => new Date(a["Due Date"]) - new Date(b["Due Date"]))
    .slice(0, 12)
    .map(row => `<tr><td class="project-name">${escapeHtml(row["Task Name"])}<span class="subtext">${escapeHtml(row.Project)}</span></td><td>${badge(row.Status)}</td><td>${badge(row.Priority)}</td><td>${shortDate(row["Due Date"])}</td><td>${row["Completion %"]}%</td></tr>`);
  const overdueRows = overdueTasks
    .sort((a, b) => new Date(a["Due Date"]) - new Date(b["Due Date"]))
    .map(row => `<tr><td class="project-name">${escapeHtml(row["Task Name"])}<span class="subtext">${escapeHtml(row.Project)}</span></td><td>${badge(row.Priority)}</td><td>${shortDate(row["Due Date"])}</td><td>${row["Completion %"]}%</td></tr>`);
  const meetingRows = upcomingMeetings.map(row => `<tr><td class="project-name">${escapeHtml(row["Meeting Type"])}<span class="subtext">${escapeHtml(row.Project)}</span></td><td>${dateTime(row["Date/Time"])}</td><td>${escapeHtml(row.Organizer)}</td><td>${escapeHtml(row["Location/Channel"])}</td><td>${escapeHtml(row.Outcome)}</td></tr>`);
  const activityRows = recentActivity.map(row => `<tr><td>${dateTime(row.Timestamp)}</td><td>${escapeHtml(row["Activity Type"])}</td><td>${escapeHtml(row.Project)}</td><td>${escapeHtml(row.Impact)}</td><td>${escapeHtml(row.Source)}</td></tr>`);

  return `
    <section class="grid kpi-grid">
      ${kpi("My projects", integer(employeeProjects.length), `${ownedProjects.length} owned`)}
      ${kpi("My tasks", integer(assignedTasks.length), `${openTasks.length} open`)}
      ${kpi("Overdue tasks", integer(overdueTasks.length), "Open tasks past due date", overdueTasks.length ? colors.red : colors.green)}
      ${kpi("Upcoming meetings", integer(upcomingMeetings.length), "Organizer or project related", colors.blue)}
      ${kpi("Task completion", pct(assignedTasks.filter(row => row.Status === "Completed").length, assignedTasks.length), "Assigned tasks completed", colors.green)}
    </section>
    <section class="grid equal-col">
      ${card("Employee information", "Matched from the Employees sheet by account email", `<div class="card-body">
        <div class="metric-pair"><span>Name</span><b>${escapeHtml(employee["Employee Name"])}</b></div>
        <div class="metric-pair"><span>Email</span><b>${escapeHtml(employee.Email)}</b></div>
        <div class="metric-pair"><span>Employee ID</span><b>${escapeHtml(employeeId)}</b></div>
        <div class="metric-pair"><span>Department</span><b>${escapeHtml(employee.Department)}</b></div>
        <div class="metric-pair"><span>Job title</span><b>${escapeHtml(employee["Job Title"])}</b></div>
        <div class="metric-pair"><span>Level</span><b>${escapeHtml(employee.Level)}</b></div>
        <div class="metric-pair"><span>Manager</span><b>${escapeHtml(employee.Manager)}</b></div>
        <div class="metric-pair"><span>Location</span><b>${escapeHtml(employee.Location)}</b></div>
        <div class="metric-pair"><span>Hire date</span><b>${shortDate(employee["Hire Date"])}</b></div>
        <div class="metric-pair"><span>Status</span><b>${escapeHtml(employee["Employment Status"])}</b></div>
      </div>`)}
      ${card("My workload", "Assigned task status and effort", `<div class="card-body">
        ${donut([
          ["Open", openTasks.length, colors.teal],
          ["Completed", assignedTasks.filter(row => row.Status === "Completed").length, colors.green],
          ["Overdue", overdueTasks.length, colors.red]
        ], assignedTasks.length, "Tasks")}
        <div class="metric-pair"><span>Estimated hours</span><b>${integer(sum(assignedTasks, "Estimated Hours"))}</b></div>
        <div class="metric-pair"><span>Recorded actual hours</span><b>${integer(sum(assignedTasks.filter(row => row["Actual Hours"] !== null), "Actual Hours"))}</b></div>
      </div>`)}
    </section>
    ${card("My projects", "Projects you own or have assigned tasks in", employeeProjects.length ? table(
      ["Project", "Status", "Risk", "Progress", "Target end"],
      projectRows
    ) : `<div class="card-body muted-empty">No related projects found.</div>`)}
    ${card("My tasks", "Assigned tasks sorted by due date", assignedTasks.length ? table(
      ["Task", "Status", "Priority", "Due date", "Completion"],
      taskRows
    ) : `<div class="card-body muted-empty">No assigned tasks found.</div>`)}
    ${card("Overdue tasks", "Open assigned tasks past due date", overdueTasks.length ? table(
      ["Task", "Priority", "Due date", "Completion"],
      overdueRows
    ) : `<div class="card-body muted-empty">No overdue assigned tasks.</div>`)}
    ${card("Upcoming meetings", "Meetings you organize or meetings for your related projects", upcomingMeetings.length ? table(
      ["Meeting", "Date/time", "Organizer", "Location", "Outcome"],
      meetingRows
    ) : `<div class="card-body muted-empty">No upcoming meetings found.</div>`)}
    ${card("Recent activity", "Latest activity for you or your related projects", recentActivity.length ? table(
      ["Time", "Activity", "Project", "Impact", "Source"],
      activityRows
    ) : `<div class="card-body muted-empty">No recent activity found.</div>`)}
  `;
}

function avatarChoicesHtml(selectedAvatar) {
  return avatars.map(([id, label]) => `
    <button class="avatar-choice ${id === selectedAvatar ? "selected" : ""}"
      type="button" data-avatar="${id}" aria-label="${escapeHtml(label)} avatar">
      <img src="${avatarSrc(id)}" alt="">
    </button>
  `).join("");
}

function uniqueAdminRows(sourceTable, valueField) {
  const seen = new Set();
  return (state.data.tables[sourceTable] || []).filter(row => {
    const value = String(row[valueField] ?? "");
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

function adminRelationConfig(tableName, header) {
  const configs = {
    Departments: {
      Director: { table: "Employees", value: "Employee Name", label: row => row["Employee Name"] }
    },
    Employees: {
      Department: { table: "Departments", value: "Department Name", label: row => row["Department Name"], fills: row => ({ "Department ID": row["Department ID"] }) },
      Manager: { table: "Employees", value: "Employee Name", label: row => row["Employee Name"] }
    },
    Projects: {
      Department: { table: "Departments", value: "Department Name", label: row => row["Department Name"], fills: row => ({ "Department ID": row["Department ID"] }) },
      Owner: { table: "Employees", value: "Employee Name", label: row => row["Employee Name"], fills: row => ({ "Owner ID": row["Employee ID"] }) }
    },
    Tasks: {
      Project: { table: "Projects", value: "Project Name", label: row => row["Project Name"], fills: row => ({ "Project ID": row["Project ID"] }) },
      "Assigned To": { table: "Employees", value: "Employee Name", label: row => row["Employee Name"], fills: row => ({ "Assigned To ID": row["Employee ID"], "Department ID": row["Department ID"], Department: row.Department }) }
    },
    Meetings: {
      Project: { table: "Projects", value: "Project Name", label: row => row["Project Name"], fills: row => ({ "Project ID": row["Project ID"] }) },
      Organizer: { table: "Employees", value: "Employee Name", label: row => row["Employee Name"], fills: row => ({ "Organizer ID": row["Employee ID"] }) }
    },
    "Weekly Updates": {
      Project: { table: "Projects", value: "Project Name", label: row => row["Project Name"], fills: row => ({ "Project ID": row["Project ID"], Department: row.Department }) }
    },
    "Activity Log": {
      Employee: { table: "Employees", value: "Employee Name", label: row => row["Employee Name"], fills: row => ({ "Employee ID": row["Employee ID"], "Department ID": row["Department ID"], Department: row.Department }) },
      Project: { table: "Projects", value: "Project Name", label: row => row["Project Name"], fills: row => ({ "Project ID": row["Project ID"] }) },
      "Task ID": { table: "Tasks", value: "Task ID", label: row => `${row["Task ID"]} - ${row["Task Name"]}`, fills: row => ({ "Project ID": row["Project ID"], Project: row.Project, "Department ID": row["Department ID"], Department: row.Department }) }
    }
  };
  return configs[tableName]?.[header] || null;
}

function adminReadonlyField(tableName, header) {
  const readonly = {
    Employees: new Set(["Department ID"]),
    Projects: new Set(["Department ID", "Owner ID"]),
    Tasks: new Set(["Project ID", "Assigned To ID", "Department ID", "Department"]),
    Meetings: new Set(["Project ID", "Organizer ID"]),
    "Weekly Updates": new Set(["Project ID", "Department"]),
    "Activity Log": new Set(["Employee ID", "Department ID", "Department", "Project ID"])
  };
  return readonly[tableName]?.has(header) || false;
}

function adminDateInputType(tableName, header) {
  const dateFields = {
    Employees: new Set(["Hire Date"]),
    Projects: new Set(["Start Date", "Target End Date"]),
    Tasks: new Set(["Due Date"]),
    Meetings: new Set(["Date/Time"]),
    "Weekly Updates": new Set(["Week Starting"]),
    "Activity Log": new Set(["Timestamp"])
  };
  if (!dateFields[tableName]?.has(header)) return "text";
  return header === "Date/Time" || header === "Timestamp" ? "datetime-local" : "date";
}

function adminDateInputValue(type, value) {
  if (!value || type === "text") return value ?? "";
  const raw = String(value).trim();
  if (type === "date") return raw.slice(0, 10);
  return raw.replace(" ", "T").slice(0, 16);
}

function cloneAdminRows(rows) {
  return rows.map(row => ({ ...row }));
}

function pushAdminHistory(entry) {
  state.adminUndoStack.push(entry);
  state.adminRedoStack = [];
}

async function restoreAdminHistoryEntry(entry, rows) {
  const payload = await adminRequest("/api/admin/restore-table", {
    table: entry.table,
    records: rows
  });
  state.data.tables = payload.tables;
  state.data.meta = payload.meta || state.data.meta;
  state.adminTable = entry.table;
  state.adminEditingRecord = null;
  return payload;
}

function adminSelectControl(tableName, header, value, required) {
  const config = adminRelationConfig(tableName, header);
  if (!config) return null;
  const options = uniqueAdminRows(config.table, config.value);
  const current = String(value ?? "");
  const hasCurrent = !current || options.some(row => String(row[config.value] ?? "") === current);
  return `
    <select name="${escapeHtml(header)}" data-admin-autofill ${required ? "required" : ""}>
      <option value="">Select ${escapeHtml(header)}</option>
      ${!hasCurrent ? `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>` : ""}
      ${options.map(row => {
        const optionValue = String(row[config.value] ?? "");
        const fills = config.fills ? config.fills(row) : {};
        return `<option value="${escapeHtml(optionValue)}" data-fills="${escapeHtml(JSON.stringify(fills))}" ${optionValue === current ? "selected" : ""}>${escapeHtml(config.label(row))}</option>`;
      }).join("")}
    </select>
  `;
}

function adminFieldControl(tableName, header, value, required, editing) {
  const autoEmployeeId = tableName === "Employees" && header === "Employee ID" && !editing;
  const select = adminSelectControl(tableName, header, value, required && !autoEmployeeId);
  if (select) return select;
  const readonly = autoEmployeeId || adminReadonlyField(tableName, header);
  const inputType = adminDateInputType(tableName, header);
  const inputValue = adminDateInputValue(inputType, value);
  return `
    <input name="${escapeHtml(header)}" type="${inputType}" value="${escapeHtml(inputValue)}"
      ${required && !autoEmployeeId ? "required" : ""}
      ${readonly ? 'readonly' : ""}
      ${autoEmployeeId ? 'placeholder="Auto-generated"' : ""}>
  `;
}

function adminPage() {
  if (!state.user?.isAdmin) {
    return card("Admin access required", "This page is only available to admins.", `
      <div class="card-body muted-empty">Your account does not have admin permission.</div>
    `);
  }
  const adminTables = ["Departments", "Employees", "Projects", "Tasks", "Meetings", "Weekly Updates", "Activity Log", "Lists"];
  const tableName = adminTables.includes(state.adminTable) ? state.adminTable : "Employees";
  state.adminTable = tableName;
  const rows = state.data.tables[tableName] || [];
  const headers = Object.keys(rows[0] || {});
  const requiredFields = new Set(state.adminRequiredFields[tableName] || []);
  const editing = state.adminEditingRecord;
  const formValues = editing || Object.fromEntries(headers.map(header => [header, ""]));
  const search = state.adminSearch.trim().toLowerCase();
  const visibleRows = search
    ? rows.filter(row => headers.some(header => String(row[header] ?? "").toLowerCase().includes(search)))
    : rows;
  const canUndo = state.adminUndoStack.length > 0;
  const canRedo = state.adminRedoStack.length > 0;
  return `
    <section class="grid settings-grid">
      ${card("Workbook data", "Add, update, or delete records in the Excel source", `
        <div class="admin-toolbar card-body">
          <label>Table
            <select id="admin-table-select">
              ${adminTables.map(name => `<option value="${escapeHtml(name)}" ${name === tableName ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}
            </select>
          </label>
          <label>Search
            <input id="admin-search-input" type="search" value="${escapeHtml(state.adminSearch)}"
              placeholder="Search ${escapeHtml(tableName)}" dir="ltr">
          </label>
          <button id="admin-new-record" class="settings-secondary-button" type="button">New record</button>
          <button id="admin-undo-record" class="settings-secondary-button admin-history-button" type="button"
            ${canUndo ? "" : "disabled"} aria-label="Undo last admin data change" title="Undo">↶</button>
          <button id="admin-redo-record" class="settings-secondary-button admin-history-button" type="button"
            ${canRedo ? "" : "disabled"} aria-label="Redo last undone admin data change" title="Redo">↷</button>
        </div>
        <form id="admin-record-form" class="admin-record-form card-body">
          <div class="admin-form-title">${editing ? "Update record" : "Add record"}</div>
          <div class="admin-field-grid">
            ${headers.map(header => {
              const autoEmployeeId = tableName === "Employees" && header === "Employee ID" && !editing;
              const required = requiredFields.has(header) && !autoEmployeeId;
              return `
              <label><span class="admin-label-text">${escapeHtml(header)}${required ? `<span class="admin-required">*</span>` : ""}</span>
                ${adminFieldControl(tableName, header, formValues[header], requiredFields.has(header), editing)}
              </label>
            `;
            }).join("")}
          </div>
          <div id="admin-record-message" class="settings-message hidden" role="status"></div>
          <div class="admin-actions">
            <button class="settings-submit" type="submit">${editing ? "Update record" : "Add record"}</button>
            ${editing ? `<button id="admin-cancel-edit" class="settings-secondary-button" type="button">Cancel edit</button>` : ""}
          </div>
        </form>
        ${table(
          [...headers.slice(0, 6), "Actions"],
          visibleRows.map(row => `<tr>
            ${headers.slice(0, 6).map(header => `<td>${escapeHtml(row[header] ?? "")}</td>`).join("")}
            <td class="admin-row-actions">
              <button type="button" data-admin-edit="${escapeHtml(row[headers[0]])}">Edit</button>
              <button type="button" data-admin-delete="${escapeHtml(row[headers[0]])}">Delete</button>
            </td>
          </tr>`)
        )}
        <div class="card-body muted-empty">Showing ${visibleRows.length} of ${rows.length} records.</div>
      `)}
      ${card("Admin access", "Grant admin access to an existing dashboard user", `
        <form id="admin-user-form" class="settings-form card-body">
          <label>User email
            <input id="admin-user-email" name="email" type="email" autocomplete="email" required>
          </label>
          <div id="admin-user-message" class="settings-message hidden" role="status"></div>
          <button class="settings-submit" type="submit">Make admin</button>
        </form>
        ${table(
          ["User", "Email", "Admin"],
          (state.adminUsers || []).map(user => `<tr>
            <td>${escapeHtml(user.displayName || user.username)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>${user.isAdmin ? badge("Admin") : "No"}</td>
          </tr>`)
        )}
      `)}
    </section>
  `;
}

function settingsPage() {
  const user = state.user || {};
  const currentAvatar = /^avatar-/.test(user.avatar || "") ? user.avatar : state.selectedSettingsAvatar;
  state.selectedSettingsAvatar = currentAvatar || "avatar-executive";
  return `
    <section class="grid settings-grid">
      ${card("Account profile", "Update the details used for dashboard access", `
        <form id="settings-profile-form" class="settings-form card-body">
          <label>Username
            <span class="settings-edit-row" data-settings-row="username">
              <span id="settings-username-value" class="settings-static-value" data-field-value="username">
                ${escapeHtml(user.username || "")}
              </span>
              <span class="settings-field-actions" data-field-actions="username">
                <button class="settings-icon-button" type="button" data-edit-field="username"
                  aria-label="Edit username">✎</button>
              </span>
            </span>
          </label>
          <label>Email
            <span class="settings-edit-row" data-settings-row="email">
              <span id="settings-email-value" class="settings-static-value" data-field-value="email">
                ${escapeHtml(user.email || "")}
              </span>
              <span class="settings-field-actions" data-field-actions="email">
                <button class="settings-icon-button" type="button" data-edit-field="email"
                  aria-label="Edit email">✎</button>
              </span>
            </span>
          </label>
          <fieldset class="avatar-fieldset">
            <legend>Avatar <span>Optional</span></legend>
            <div id="settings-avatar-grid" class="avatar-grid settings-avatar-grid">${avatarChoicesHtml(state.selectedSettingsAvatar)}</div>
          </fieldset>
          <button class="settings-submit" type="submit">Save avatar</button>
          <div id="settings-profile-message" class="settings-message hidden" role="status"></div>
          <div class="settings-meta">
            <div class="metric-pair"><span>Date joined</span><b>${dateTime(user.dateJoined)}</b></div>
            <div class="metric-pair"><span>Last login</span><b>${dateTime(user.lastLogin)}</b></div>
          </div>
        </form>
      `)}
      ${card("Password settings", "Use your current password to set a new one", `
        <div class="settings-form card-body">
          <button id="show-password-change" class="settings-secondary-button" type="button">Change password</button>
        </div>
        <form id="settings-password-form" class="settings-form card-body hidden">
          <label>Current password
            <span class="password-wrap">
              <input id="settings-current-password" name="currentPassword" type="password"
                autocomplete="current-password" required>
              <button class="password-toggle" type="button" aria-label="Show password"
                data-target="settings-current-password">👁</button>
            </span>
          </label>
          <label>New password
            <span class="password-wrap">
              <input id="settings-new-password" name="password" type="password"
                autocomplete="new-password" required>
              <button class="password-toggle" type="button" aria-label="Show password"
                data-target="settings-new-password">👁</button>
            </span>
          </label>
          <label>Confirm new password
            <span class="password-wrap">
              <input id="settings-confirm-password" name="confirmPassword" type="password"
                autocomplete="new-password" required>
              <button class="password-toggle" type="button" aria-label="Show password"
                data-target="settings-confirm-password">👁</button>
            </span>
          </label>
          <div id="settings-password-message" class="settings-message hidden" role="status"></div>
          <button class="settings-submit" type="submit">Update password</button>
        </form>
      `)}
    </section>
  `;
}

function render() {
  if (!state.data) return;
  if (protectedPages.has(state.page) && !state.user) {
    state.pendingPage = state.page;
    state.page = "overview";
    setActiveNav("overview");
    openAuthModal("signup");
  }
  if (state.page === "admin" && !state.user?.isAdmin) {
    state.page = "overview";
    setActiveNav("overview");
  }
  const d = filteredTables();
  const renderers = { overview: portfolioOverview, delivery: deliveryPage, workforce: workforcePage, governance: governancePage, settings: settingsPage, "my-dashboard": myDashboardPage, admin: adminPage };
  document.getElementById("dashboard-content").innerHTML = renderers[state.page](d);
  document.getElementById("page-title").textContent = pageInfo[state.page][0];
  document.getElementById("page-subtitle").textContent = pageInfo[state.page][1];
  if (state.page === "settings") bindSettingsPage();
  if (state.page === "admin") bindAdminPage();
}

function setActiveNav(page) {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.dataset.page === page);
  });
}

async function loadData() {
  const button = document.getElementById("refresh-button");
  const alert = document.getElementById("alert");
  button.classList.add("loading"); button.disabled = true;
  alert.classList.add("hidden");
  if (!state.data) document.getElementById("dashboard-content").innerHTML = `<div class="loading-state"><div class="loader"></div>Reading Excel tables…</div>`;
  try {
    if (window.location.protocol === "file:") {
      throw new Error("This dashboard cannot be opened as a file. Run start_dashboard.sh, then open the http:// address it displays.");
    }
    const response = await fetch(`/api/data?t=${Date.now()}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Data request failed");
    state.data = payload;
    const departments = payload.tables.Departments.map(row => row["Department Name"]).sort();
    if (state.department !== "All" && !departments.includes(state.department)) {
      state.department = "All";
    }
    document.getElementById("department-filter").innerHTML = `<option value="All">All departments</option>${departments.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("")}`;
    document.getElementById("department-filter").value = state.department;
    document.getElementById("source-file").textContent = payload.meta.source;
    const dated = [...payload.tables["Activity Log"].map(r=>r.Timestamp), ...payload.tables.Meetings.map(r=>r["Date/Time"])];
    document.getElementById("reporting-date").textContent = shortDate(dated.sort().at(-1));
    const count = Object.entries(payload.tables).filter(([name])=>name!=="Lists").reduce((a,[,rows])=>a+rows.length,0);
    document.getElementById("record-count").textContent = integer(count);
    const sourceModified = new Date(payload.meta.modifiedUtc).toLocaleString([], {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"
    });
    const refreshed = new Date(payload.meta.refreshedUtc).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    document.getElementById("last-refresh").textContent = `Excel saved ${sourceModified} · Refreshed ${refreshed}`;
    render();
  } catch (error) {
    const message = error instanceof TypeError && error.message === "Failed to fetch"
      ? "The dashboard server is not reachable. Start it with start_dashboard.sh and use the http://127.0.0.1:8000 address."
      : error.message;
    alert.textContent = `Unable to refresh the workbook: ${message}`;
    alert.classList.remove("hidden");
    document.getElementById("dashboard-content").innerHTML = "";
  } finally {
    button.classList.remove("loading"); button.disabled = false;
  }
}

document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click", () => {
  const requestedPage = button.dataset.page;
  if (protectedPages.has(requestedPage) && !state.user) {
    state.pendingPage = requestedPage;
    openAuthModal("signup");
    return;
  }
  state.page = requestedPage;
  setActiveNav(requestedPage);
  render();
}));
document.getElementById("department-filter").addEventListener("change", event => { state.department = event.target.value; render(); });
document.getElementById("refresh-button").addEventListener("click", loadData);

const auth = {
  modal: document.getElementById("auth-modal"),
  backdrop: document.getElementById("auth-backdrop"),
  title: document.getElementById("auth-title"),
  subtitle: document.getElementById("auth-subtitle"),
  message: document.getElementById("auth-message"),
  close: document.getElementById("auth-close"),
  loginButton: document.getElementById("login-button"),
  signupButton: document.getElementById("signup-button"),
  myDashboardButton: document.getElementById("my-dashboard-button"),
  adminButton: document.getElementById("admin-button"),
  settingsButton: document.getElementById("settings-button"),
  logoutButton: document.getElementById("logout-button"),
  userMenu: document.getElementById("user-menu"),
  userMenuButton: document.getElementById("user-menu-button"),
  userMenuDropdown: document.getElementById("user-menu-dropdown"),
  userLabel: document.getElementById("auth-user"),
  userAvatar: document.getElementById("user-avatar"),
  userMenuAvatar: document.getElementById("user-menu-avatar"),
  userMenuName: document.getElementById("user-menu-name"),
  userMenuEmail: document.getElementById("user-menu-email"),
  loginForm: document.getElementById("login-form"),
  signupForm: document.getElementById("signup-form"),
  signupOtpForm: document.getElementById("signup-otp-form"),
  forgotForm: document.getElementById("forgot-form"),
  resetForm: document.getElementById("reset-form"),
  otpBoxes: [...document.querySelectorAll(".otp-box")]
};

function avatarSrc(avatar) {
  if (/^https?:\/\//.test(avatar || "")) return avatar;
  return `avatars/${avatar || "avatar-executive"}.svg`;
}

function showAuthMessage(text, type = "") {
  auth.message.textContent = text;
  auth.message.className = `auth-message ${type}`.trim();
  auth.message.classList.remove("hidden");
}

function clearAuthMessage() {
  auth.message.textContent = "";
  auth.message.className = "auth-message hidden";
}

function setAuthMode(mode) {
  clearAuthMessage();
  auth.loginForm.classList.toggle("hidden", mode !== "login");
  auth.signupForm.classList.toggle("hidden", mode !== "signup");
  auth.signupOtpForm.classList.toggle("hidden", mode !== "signup-otp");
  auth.forgotForm.classList.toggle("hidden", mode !== "forgot");
  auth.resetForm.classList.toggle("hidden", mode !== "reset");
  if (mode === "signup") {
    auth.title.textContent = "Sign up";
    auth.subtitle.textContent = "Create a local dashboard account.";
    clearSignupRequiredState();
    renderAvatarChoices();
    document.getElementById("signup-user-name").focus();
  } else if (mode === "signup-otp") {
    auth.title.textContent = "Verify email";
    auth.subtitle.textContent = "Enter the verification code we sent to your email.";
    auth.otpBoxes[0].focus();
  } else if (mode === "forgot") {
    auth.title.textContent = "Reset password";
    auth.subtitle.textContent = "Enter your username or email and we’ll send a reset email.";
    document.getElementById("forgot-identifier").focus();
  } else if (mode === "reset") {
    auth.title.textContent = "Create new password";
    auth.subtitle.textContent = "Enter and confirm your new dashboard password.";
    document.getElementById("reset-password").focus();
  } else {
    auth.title.textContent = "Login";
    auth.subtitle.textContent = "Welcome! Please sign in to continue.";
    document.getElementById("login-identifier").focus();
  }
}

function updateOtpValue() {
  document.getElementById("signup-otp-code").value = auth.otpBoxes.map(box => box.value).join("");
}

function clearOtpBoxes() {
  auth.otpBoxes.forEach(box => { box.value = ""; });
  updateOtpValue();
}

function clearSignupRequiredState() {
  auth.signupForm.querySelectorAll("[data-required-field]").forEach(label => {
    label.classList.remove("invalid");
    const input = label.querySelector("input");
    input.setAttribute("aria-invalid", "false");
  });
  document.getElementById("signup-required-summary").classList.add("hidden");
}

function openAuthModal(mode = "login") {
  auth.modal.hidden = false;
  auth.backdrop.hidden = false;
  document.body.classList.add("auth-modal-open");
  auth.modal.setAttribute("aria-hidden", "false");
  setAuthMode(mode);
}

function closeAuthModal() {
  auth.modal.hidden = true;
  auth.backdrop.hidden = true;
  document.body.classList.remove("auth-modal-open");
  auth.modal.setAttribute("aria-hidden", "true");
  clearAuthMessage();
}

function renderAuthState() {
  const loggedIn = Boolean(state.user);
  auth.loginButton.classList.toggle("hidden", loggedIn);
  auth.signupButton.classList.toggle("hidden", loggedIn);
  auth.userMenu.classList.toggle("hidden", !loggedIn);
  auth.userLabel.textContent = loggedIn ? state.user.displayName || state.user.username : "";
  if (loggedIn) {
    const src = avatarSrc(state.user.avatar);
    auth.userAvatar.src = src;
    auth.userMenuAvatar.src = src;
    auth.userMenuName.textContent = state.user.displayName || state.user.username;
    auth.userMenuEmail.textContent = state.user.email || "";
    auth.adminButton.classList.toggle("hidden", !state.user.isAdmin);
  } else {
    auth.userMenuDropdown.hidden = true;
    auth.userMenuButton.setAttribute("aria-expanded", "false");
    auth.adminButton.classList.add("hidden");
  }
}

async function authRequest(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || payload.message || "Authentication failed.");
  return payload;
}

async function adminRequest(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Admin request failed.");
  return payload;
}

async function loadAdminData() {
  const response = await fetch("/api/admin/data", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Admin data request failed.");
  state.adminUsers = payload.users || [];
  state.adminRequiredFields = payload.requiredFields || state.adminRequiredFields;
  if (payload.tables) {
    state.data.tables = payload.tables;
    state.data.meta = payload.meta || state.data.meta;
  }
  return payload;
}

function continueAfterAuth() {
  closeAuthModal();
  if (state.pendingPage) {
    state.page = state.pendingPage;
    state.pendingPage = null;
    setActiveNav(state.page);
    render();
  }
  if (state.pendingAssistant) {
    state.pendingAssistant = false;
    setAssistantOpen(true);
  }
}

function showSettingsMessage(element, text, type = "") {
  if (!element) return;
  element.textContent = text;
  element.className = `settings-message ${type}`.trim();
  element.classList.remove("hidden");
}

function settingsFieldValue(field) {
  const input = document.getElementById(field === "email" ? "settings-email" : "settings-username");
  if (input) return input.value.trim();
  return document.getElementById(`settings-${field}-value`).textContent.trim();
}

function restoreSettingsField(field, value) {
  const valueElement = document.querySelector(`[data-field-value="${field}"]`);
  const actions = document.querySelector(`[data-field-actions="${field}"]`);
  if (!valueElement || !actions) return;
  valueElement.textContent = value;
  actions.innerHTML = `
    <button class="settings-icon-button" type="button" data-edit-field="${field}"
      aria-label="Edit ${field}">✎</button>
  `;
}

async function saveSettingsField(field) {
  const input = document.getElementById(field === "email" ? "settings-email" : "settings-username");
  const message = document.getElementById("settings-profile-message");
  const actions = document.querySelector(`[data-field-actions="${field}"]`);
  if (!input || !actions) return;
  actions.querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    const payload = await authRequest("/api/auth/settings/profile", {
      username: field === "username" ? input.value : settingsFieldValue("username"),
      email: field === "email" ? input.value : settingsFieldValue("email"),
      avatar: state.selectedSettingsAvatar
    });
    state.user = payload.user;
    state.selectedSettingsAvatar = /^avatar-/.test(state.user.avatar || "")
      ? state.user.avatar
      : state.selectedSettingsAvatar;
    restoreSettingsField("username", state.user.username || "");
    restoreSettingsField("email", state.user.email || "");
    renderAuthState();
    showSettingsMessage(message, `${field === "email" ? "Email" : "Username"} updated.`, "success");
  } catch (error) {
    showSettingsMessage(message, error.message, "error");
    actions.querySelectorAll("button").forEach(button => { button.disabled = false; });
  }
}

function bindSettingsPage() {
  const avatarGrid = document.getElementById("settings-avatar-grid");
  const profileForm = document.getElementById("settings-profile-form");
  const passwordForm = document.getElementById("settings-password-form");
  const showPasswordChange = document.getElementById("show-password-change");
  if (profileForm) {
    profileForm.addEventListener("click", event => {
      const editButton = event.target.closest("[data-edit-field]");
      if (editButton) {
        const field = editButton.dataset.editField;
        const value = document.querySelector(`[data-field-value="${field}"]`);
        const actions = document.querySelector(`[data-field-actions="${field}"]`);
        if (!value || !actions || value.querySelector("input")) return;
        const currentValue = value.textContent.trim();
        const input = document.createElement("input");
        input.id = field === "email" ? "settings-email" : "settings-username";
        input.name = field;
        input.type = field === "email" ? "email" : "text";
        input.autocomplete = field === "email" ? "email" : "username";
        input.required = true;
        input.value = currentValue;
        value.replaceChildren(input);
        actions.innerHTML = `
          <button class="settings-mini-button save" type="button" data-save-field="${field}">Save</button>
          <button class="settings-mini-button cancel" type="button" data-cancel-field="${field}">Cancel</button>
        `;
        input.focus();
        input.select();
        return;
      }
      const saveButton = event.target.closest("[data-save-field]");
      if (saveButton) {
        saveSettingsField(saveButton.dataset.saveField);
        return;
      }
      const cancelButton = event.target.closest("[data-cancel-field]");
      if (cancelButton) {
        const field = cancelButton.dataset.cancelField;
        restoreSettingsField(field, field === "email" ? state.user.email || "" : state.user.username || "");
      }
    });
    profileForm.addEventListener("keydown", event => {
      const input = event.target.closest("#settings-username, #settings-email");
      if (!input) return;
      if (event.key === "Enter") {
        event.preventDefault();
        saveSettingsField(input.name);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        restoreSettingsField(input.name, input.name === "email" ? state.user.email || "" : state.user.username || "");
      }
    });
  }
  if (showPasswordChange && passwordForm) {
    showPasswordChange.addEventListener("click", () => {
      showPasswordChange.closest(".settings-form").classList.add("hidden");
      passwordForm.classList.remove("hidden");
      document.getElementById("settings-current-password").focus();
    });
  }
  if (avatarGrid) {
    avatarGrid.querySelectorAll(".avatar-choice").forEach(button => {
      button.addEventListener("click", () => {
        state.selectedSettingsAvatar = button.dataset.avatar;
        avatarGrid.querySelectorAll(".avatar-choice").forEach(item => {
          item.classList.toggle("selected", item === button);
        });
      });
    });
  }
  if (profileForm) {
    profileForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = profileForm.querySelector(".settings-submit");
      const message = document.getElementById("settings-profile-message");
      submit.disabled = true;
      try {
        const payload = await authRequest("/api/auth/settings/profile", {
          username: document.getElementById("settings-username")?.value
            || document.getElementById("settings-username-value").textContent.trim(),
          email: document.getElementById("settings-email")?.value
            || document.getElementById("settings-email-value").textContent.trim(),
          avatar: state.selectedSettingsAvatar
        });
        state.user = payload.user;
        state.selectedSettingsAvatar = /^avatar-/.test(state.user.avatar || "")
          ? state.user.avatar
          : state.selectedSettingsAvatar;
        renderAuthState();
        render();
        showSettingsMessage(document.getElementById("settings-profile-message"), "Profile updated.", "success");
      } catch (error) {
        showSettingsMessage(message, error.message, "error");
      } finally {
        submit.disabled = false;
      }
    });
  }
  if (passwordForm) {
    passwordForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = passwordForm.querySelector(".settings-submit");
      const message = document.getElementById("settings-password-message");
      submit.disabled = true;
      try {
        const payload = await authRequest("/api/auth/settings/password", {
          currentPassword: document.getElementById("settings-current-password").value,
          password: document.getElementById("settings-new-password").value,
          confirmPassword: document.getElementById("settings-confirm-password").value
        });
        passwordForm.reset();
        showSettingsMessage(message, payload.message || "Password updated.", "success");
      } catch (error) {
        showSettingsMessage(message, error.message, "error");
      } finally {
        submit.disabled = false;
      }
    });
  }
}

function bindAdminPage() {
  const tableSelect = document.getElementById("admin-table-select");
  const searchInput = document.getElementById("admin-search-input");
  const newButton = document.getElementById("admin-new-record");
  const undoButton = document.getElementById("admin-undo-record");
  const redoButton = document.getElementById("admin-redo-record");
  const recordForm = document.getElementById("admin-record-form");
  const userForm = document.getElementById("admin-user-form");
  const recordMessage = document.getElementById("admin-record-message");
  const userMessage = document.getElementById("admin-user-message");
  if (tableSelect) {
    tableSelect.addEventListener("change", () => {
      state.adminTable = tableSelect.value;
      state.adminSearch = "";
      state.adminEditingRecord = null;
      render();
    });
  }
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.adminSearch = searchInput.value;
      state.adminEditingRecord = null;
      render();
      const updatedInput = document.getElementById("admin-search-input");
      if (updatedInput) {
        updatedInput.focus();
        updatedInput.setSelectionRange(updatedInput.value.length, updatedInput.value.length);
      }
    });
  }
  if (newButton) {
    newButton.addEventListener("click", () => {
      state.adminEditingRecord = null;
      render();
    });
  }
  if (undoButton) {
    undoButton.addEventListener("click", async () => {
      const entry = state.adminUndoStack.pop();
      if (!entry) return;
      undoButton.disabled = true;
      try {
        await restoreAdminHistoryEntry(entry, entry.beforeRows);
        state.adminRedoStack.push(entry);
        render();
      } catch (error) {
        state.adminUndoStack.push(entry);
        showSettingsMessage(recordMessage, error.message, "error");
        undoButton.disabled = false;
      }
    });
  }
  if (redoButton) {
    redoButton.addEventListener("click", async () => {
      const entry = state.adminRedoStack.pop();
      if (!entry) return;
      redoButton.disabled = true;
      try {
        await restoreAdminHistoryEntry(entry, entry.afterRows);
        state.adminUndoStack.push(entry);
        render();
      } catch (error) {
        state.adminRedoStack.push(entry);
        showSettingsMessage(recordMessage, error.message, "error");
        redoButton.disabled = false;
      }
    });
  }
  document.querySelectorAll("[data-admin-autofill]").forEach(select => {
    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      if (!option?.dataset.fills) return;
      try {
        const fills = JSON.parse(option.dataset.fills);
        Object.entries(fills).forEach(([field, value]) => {
          const input = [...(recordForm?.elements || [])].find(element => element.name === field);
          if (input) input.value = value ?? "";
        });
      } catch {
        // Ignore malformed autofill metadata; backend validation still applies.
      }
    });
  });
  document.querySelectorAll("[data-admin-edit]").forEach(button => {
    button.addEventListener("click", () => {
      const rows = state.data.tables[state.adminTable] || [];
      const headers = Object.keys(rows[0] || {});
      const key = headers[0];
      state.adminEditingRecord = rows.find(row => String(row[key]) === button.dataset.adminEdit) || null;
      render();
    });
  });
  document.querySelectorAll("[data-admin-delete]").forEach(button => {
    button.addEventListener("click", async () => {
      const rows = state.data.tables[state.adminTable] || [];
      const headers = Object.keys(rows[0] || {});
      const key = headers[0];
      const record = rows.find(row => String(row[key]) === button.dataset.adminDelete);
      if (!record || !window.confirm(`Delete ${state.adminTable} record ${record[key]}?`)) return;
      const tableName = state.adminTable;
      const beforeRows = cloneAdminRows(rows);
      try {
        const payload = await adminRequest("/api/admin/record", {
          table: tableName,
          action: "delete",
          record
        });
        state.data.tables = payload.tables;
        state.data.meta = payload.meta || state.data.meta;
        pushAdminHistory({
          table: tableName,
          beforeRows,
          afterRows: cloneAdminRows(payload.tables[tableName] || [])
        });
        state.adminEditingRecord = null;
        render();
      } catch (error) {
        showSettingsMessage(recordMessage, error.message, "error");
      }
    });
  });
  document.getElementById("admin-cancel-edit")?.addEventListener("click", () => {
    state.adminEditingRecord = null;
    render();
  });
  if (recordForm) {
    recordForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = recordForm.querySelector(".settings-submit");
      submit.disabled = true;
      const record = Object.fromEntries(new FormData(recordForm).entries());
      const tableName = state.adminTable;
      const beforeRows = cloneAdminRows(state.data.tables[tableName] || []);
      try {
        const payload = await adminRequest("/api/admin/record", {
          table: tableName,
          action: state.adminEditingRecord ? "update" : "add",
          record
        });
        state.data.tables = payload.tables;
        state.data.meta = payload.meta || state.data.meta;
        pushAdminHistory({
          table: tableName,
          beforeRows,
          afterRows: cloneAdminRows(payload.tables[tableName] || [])
        });
        state.adminEditingRecord = null;
        render();
      } catch (error) {
        showSettingsMessage(recordMessage, error.message, "error");
      } finally {
        submit.disabled = false;
      }
    });
  }
  if (userForm) {
    userForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = userForm.querySelector(".settings-submit");
      submit.disabled = true;
      try {
        const payload = await adminRequest("/api/admin/set-admin", {
          email: document.getElementById("admin-user-email").value,
          isAdmin: true
        });
        state.adminUsers = payload.users || [];
        userForm.reset();
        render();
      } catch (error) {
        showSettingsMessage(userMessage, error.message, "error");
      } finally {
        submit.disabled = false;
      }
    });
  }
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/auth/me", { cache: "no-store" });
    const payload = await response.json();
    state.user = payload.user || null;
  } catch {
    state.user = null;
  }
  renderAuthState();
}

auth.loginButton.addEventListener("click", () => openAuthModal("login"));
auth.signupButton.addEventListener("click", () => openAuthModal("signup"));
auth.close.addEventListener("click", closeAuthModal);
auth.backdrop.addEventListener("click", closeAuthModal);
document.getElementById("show-signup-link").addEventListener("click", () => setAuthMode("signup"));
document.getElementById("show-login-link").addEventListener("click", () => setAuthMode("login"));
document.getElementById("otp-signup-link").addEventListener("click", () => setAuthMode("signup"));
document.getElementById("forgot-login-link").addEventListener("click", () => setAuthMode("login"));
document.getElementById("forgot-password-link").addEventListener("click", () => setAuthMode("forgot"));
document.querySelectorAll(".google-placeholder").forEach(button => {
  button.addEventListener("click", () => {
    window.location.href = "/api/auth/google/start";
  });
});

function renderAvatarChoices() {
  const grid = document.getElementById("avatar-grid");
  grid.innerHTML = avatarChoicesHtml(state.selectedAvatar);
  grid.querySelectorAll(".avatar-choice").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedAvatar = button.dataset.avatar;
      grid.querySelectorAll(".avatar-choice").forEach(item => {
        item.classList.toggle("selected", item === button);
      });
    });
  });
}
renderAvatarChoices();

function validateSignupRequiredFields() {
  let firstEmpty = null;
  auth.signupForm.querySelectorAll("[data-required-field]").forEach(label => {
    const input = label.querySelector("input");
    const empty = !input.value.trim();
    label.classList.toggle("invalid", empty);
    input.setAttribute("aria-invalid", String(empty));
    if (empty && !firstEmpty) firstEmpty = input;
  });
  document.getElementById("signup-required-summary").classList.toggle("hidden", !firstEmpty);
  if (firstEmpty) firstEmpty.focus();
  return !firstEmpty;
}

auth.signupForm.querySelectorAll("[data-required-field] input").forEach(input => {
  input.addEventListener("input", () => {
    if (input.value.trim()) {
      const label = input.closest("[data-required-field]");
      label.classList.remove("invalid");
      input.setAttribute("aria-invalid", "false");
      const hasInvalid = [...auth.signupForm.querySelectorAll("[data-required-field]")]
        .some(fieldLabel => fieldLabel.classList.contains("invalid"));
      document.getElementById("signup-required-summary").classList.toggle("hidden", !hasInvalid);
    }
  });
});

auth.userMenuButton.addEventListener("click", () => {
  const open = auth.userMenuDropdown.hidden;
  auth.userMenuDropdown.hidden = !open;
  auth.userMenuButton.setAttribute("aria-expanded", String(open));
});
auth.myDashboardButton.addEventListener("click", () => {
  auth.userMenuDropdown.hidden = true;
  auth.userMenuButton.setAttribute("aria-expanded", "false");
  state.page = "my-dashboard";
  state.pendingPage = null;
  setActiveNav("my-dashboard");
  render();
});
auth.adminButton.addEventListener("click", async () => {
  if (!state.user?.isAdmin) return;
  auth.userMenuDropdown.hidden = true;
  auth.userMenuButton.setAttribute("aria-expanded", "false");
  try {
    await loadAdminData();
    state.page = "admin";
    state.pendingPage = null;
    setActiveNav("admin");
    render();
  } catch (error) {
    const alert = document.getElementById("alert");
    alert.textContent = error.message;
    alert.classList.remove("hidden");
  }
});
auth.settingsButton.addEventListener("click", () => {
  auth.userMenuDropdown.hidden = true;
  auth.userMenuButton.setAttribute("aria-expanded", "false");
  state.page = "settings";
  state.pendingPage = null;
  state.selectedSettingsAvatar = /^avatar-/.test(state.user?.avatar || "")
    ? state.user.avatar
    : "avatar-executive";
  setActiveNav("settings");
  render();
});
document.addEventListener("click", event => {
  if (!auth.userMenu.contains(event.target)) {
    auth.userMenuDropdown.hidden = true;
    auth.userMenuButton.setAttribute("aria-expanded", "false");
  }
});

auth.loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = auth.loginForm.querySelector(".auth-submit");
  submit.disabled = true;
  clearAuthMessage();
  try {
    const payload = await authRequest("/api/auth/login", {
      identifier: document.getElementById("login-identifier").value,
      password: document.getElementById("login-password").value
    });
    state.user = payload.user;
    renderAuthState();
    auth.loginForm.reset();
    continueAfterAuth();
  } catch (error) {
    showAuthMessage(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

auth.signupForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!validateSignupRequiredFields()) return;
  const submit = auth.signupForm.querySelector(".auth-submit");
  submit.disabled = true;
  clearAuthMessage();
  try {
    const username = document.getElementById("signup-user-name").value;
    const payload = await authRequest("/api/auth/signup", {
      displayName: username,
      username,
      email: document.getElementById("signup-email").value,
      avatar: state.selectedAvatar,
      password: document.getElementById("signup-password").value,
      confirmPassword: document.getElementById("signup-confirm-password").value
    });
    state.signupOtpEmail = payload.email || document.getElementById("signup-email").value;
    document.getElementById("signup-otp-email").value = state.signupOtpEmail;
    auth.signupForm.reset();
    clearSignupRequiredState();
    state.selectedAvatar = "avatar-executive";
    clearOtpBoxes();
    setAuthMode("signup-otp");
    showAuthMessage(payload.message || "We sent a verification code to your email.", "success");
  } catch (error) {
    showAuthMessage(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

auth.signupOtpForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = auth.signupOtpForm.querySelector(".auth-submit");
  submit.disabled = true;
  clearAuthMessage();
  try {
    updateOtpValue();
    const payload = await authRequest("/api/auth/verify-signup", {
      email: document.getElementById("signup-otp-email").value,
      otp: document.getElementById("signup-otp-code").value
    });
    state.user = payload.user;
    state.signupOtpEmail = null;
    renderAuthState();
    auth.signupOtpForm.reset();
    clearOtpBoxes();
    continueAfterAuth();
  } catch (error) {
    showAuthMessage(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

auth.otpBoxes.forEach((box, index) => {
  box.addEventListener("input", () => {
    box.value = box.value.replace(/\D/g, "").slice(-1);
    updateOtpValue();
    if (box.value && index < auth.otpBoxes.length - 1) {
      auth.otpBoxes[index + 1].focus();
    }
  });
  box.addEventListener("keydown", event => {
    if (event.key === "Backspace" && !box.value && index > 0) {
      auth.otpBoxes[index - 1].focus();
    }
    if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      auth.otpBoxes[index - 1].focus();
    }
    if (event.key === "ArrowRight" && index < auth.otpBoxes.length - 1) {
      event.preventDefault();
      auth.otpBoxes[index + 1].focus();
    }
  });
  box.addEventListener("paste", event => {
    event.preventDefault();
    const digits = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!digits) return;
    auth.otpBoxes.forEach((otpBox, otpIndex) => {
      otpBox.value = digits[otpIndex] || "";
    });
    updateOtpValue();
    auth.otpBoxes[Math.min(digits.length, auth.otpBoxes.length) - 1].focus();
  });
});

document.addEventListener("click", event => {
  const button = event.target.closest(".password-toggle");
  if (!button) return;
  const input = document.getElementById(button.dataset.target);
  if (!input) return;
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  button.textContent = showing ? "👁" : "✕";
  input.focus();
});

auth.forgotForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = auth.forgotForm.querySelector(".auth-submit");
  submit.disabled = true;
  clearAuthMessage();
  try {
    const payload = await authRequest("/api/auth/forgot-password", {
      identifier: document.getElementById("forgot-identifier").value
    });
    auth.forgotForm.reset();
    showAuthMessage(payload.message || "Password reset email sent.", "success");
  } catch (error) {
    showAuthMessage(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

auth.resetForm.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = auth.resetForm.querySelector(".auth-submit");
  submit.disabled = true;
  clearAuthMessage();
  try {
    await authRequest("/api/auth/reset-password", {
      token: state.resetToken || "",
      password: document.getElementById("reset-password").value,
      confirmPassword: document.getElementById("reset-confirm-password").value
    });
    state.resetToken = null;
    auth.resetForm.reset();
    window.history.replaceState({}, document.title, window.location.pathname);
    setAuthMode("login");
    showAuthMessage("Password updated. Please log in with your new password.", "success");
  } catch (error) {
    showAuthMessage(error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

auth.logoutButton.addEventListener("click", async () => {
  auth.logoutButton.disabled = true;
  try {
    await authRequest("/api/auth/logout");
  } finally {
    state.user = null;
    state.pendingPage = null;
    state.pendingAssistant = false;
    renderAuthState();
    setAssistantOpen(false);
    if (protectedPages.has(state.page)) {
      state.page = "overview";
      setActiveNav("overview");
      render();
    }
    auth.logoutButton.disabled = false;
  }
});

loadCurrentUser();
loadData();
const queryParams = new URLSearchParams(window.location.search);
state.resetToken = queryParams.get("reset_token");
if (state.resetToken) openAuthModal("reset");
const googleError = queryParams.get("google_error");
if (googleError) {
  openAuthModal("signup");
  showAuthMessage(
    googleError === "employee_only"
      ? "Sorry, you can not sign up because this email is not registered as a company employee."
      : "Google sign-in could not be completed. Please try again.",
    "error"
  );
  window.history.replaceState({}, document.title, window.location.pathname);
}

const assistant = {
  panel: document.getElementById("assistant-panel"),
  toggle: document.getElementById("assistant-toggle"),
  close: document.getElementById("assistant-close"),
  backdrop: document.getElementById("assistant-backdrop"),
  messages: document.getElementById("assistant-messages"),
  form: document.getElementById("assistant-form"),
  input: document.getElementById("assistant-input"),
  send: document.getElementById("assistant-send"),
  history: []
};

function setAssistantOpen(open) {
  if (open && !state.user) {
    state.pendingAssistant = true;
    openAuthModal("signup");
    return;
  }
  assistant.panel.setAttribute("aria-hidden", String(!open));
  assistant.toggle.setAttribute("aria-expanded", String(open));
  if (open) {
    assistant.panel.hidden = false;
    assistant.backdrop.hidden = false;
    // Ensure the off-canvas initial state is painted before starting transition.
    void assistant.panel.offsetWidth;
    assistant.panel.classList.add("open");
    assistant.input.focus();
  } else {
    assistant.panel.classList.remove("open");
    assistant.backdrop.hidden = true;
    window.setTimeout(() => {
      if (!assistant.panel.classList.contains("open")) assistant.panel.hidden = true;
    }, 230);
    assistant.toggle.focus();
  }
}

function appendAssistantFormattedText(element, content) {
  const parts = String(content).split(/(\*\*[^*\n]+\*\*)/g);
  parts.forEach(part => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      element.appendChild(strong);
    } else {
      element.appendChild(document.createTextNode(part));
    }
  });
}

function addAssistantMessage(role, content, context = null) {
  const row = document.createElement("article");
  row.className = `assistant-message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "assistant-bubble";
  appendAssistantFormattedText(bubble, content);
  if (context && role === "assistant") {
    const meta = document.createElement("div");
    meta.className = "assistant-message-meta";
    meta.textContent = context.department === "All"
      ? `Source: ${context.workbook} · All departments`
      : `Source: ${context.workbook} · ${context.department}`;
    bubble.appendChild(meta);
  }
  row.appendChild(bubble);
  assistant.messages.appendChild(row);
  assistant.messages.scrollTop = assistant.messages.scrollHeight;
  return row;
}

function addAssistantTyping() {
  const row = document.createElement("article");
  row.className = "assistant-message assistant";
  row.setAttribute("aria-label", "Dashboard Assistant is responding");
  const bubble = document.createElement("div");
  bubble.className = "assistant-bubble";
  bubble.innerHTML = '<span class="assistant-typing"><i></i><i></i><i></i></span>';
  row.appendChild(bubble);
  assistant.messages.appendChild(row);
  assistant.messages.scrollTop = assistant.messages.scrollHeight;
  return row;
}

function resizeAssistantInput() {
  assistant.input.style.height = "auto";
  assistant.input.style.height = `${Math.min(assistant.input.scrollHeight, 120)}px`;
}

async function sendAssistantMessage(text) {
  const message = text.trim();
  if (!message || assistant.send.disabled) return;
  if (!state.user) {
    state.pendingAssistant = true;
    openAuthModal("signup");
    return;
  }
  if (!state.data) {
    addAssistantMessage("assistant", "Wait for the dashboard data to finish loading.");
    return;
  }

  addAssistantMessage("user", message);
  assistant.history.push({ role: "user", content: message });
  assistant.input.value = "";
  resizeAssistantInput();
  assistant.send.disabled = true;
  const typing = addAssistantTyping();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: assistant.history.slice(-8, -1),
        department: state.department,
        page: state.page
      })
    });
    const data = await response.json();
    typing.remove();
    if (!response.ok) {
      throw new Error(data.message || data.error || "The assistant is unavailable.");
    }
    addAssistantMessage("assistant", data.answer, data.context);
    assistant.history.push({ role: "assistant", content: data.answer });
  } catch (error) {
    typing.remove();
    addAssistantMessage(
      "assistant",
      error.message || "I couldn’t connect to the dashboard assistant."
    );
  } finally {
    assistant.send.disabled = false;
    assistant.input.focus();
  }
}

assistant.toggle.addEventListener("click", () => setAssistantOpen(true));
assistant.close.addEventListener("click", () => setAssistantOpen(false));
assistant.backdrop.addEventListener("click", () => setAssistantOpen(false));
assistant.form.addEventListener("submit", event => {
  event.preventDefault();
  sendAssistantMessage(assistant.input.value);
});
assistant.input.addEventListener("input", resizeAssistantInput);
assistant.input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    assistant.form.requestSubmit();
  }
});
document.querySelectorAll(".assistant-suggestions button").forEach(button => {
  button.addEventListener("click", () => sendAssistantMessage(button.textContent));
});
