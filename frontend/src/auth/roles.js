// Where each role lands after sign-in. The role always comes from /auth/me
// (the server's database account), never from anything the user picks.
export const ROLE_HOME = {
  student: '/student',
  teaching_staff: '/teaching',
  non_teaching_staff: '/non-teaching',
  department_authority: '/authority',
  higher_authority: '/higher-authority',
  viewer: '/viewer',
  admin: '/admin',
}

export const ROLE_LABEL = {
  student: 'Student',
  teaching_staff: 'Teaching Staff',
  non_teaching_staff: 'Non-Teaching Staff',
  department_authority: 'Department Authority',
  higher_authority: 'Higher Authority',
  viewer: 'View-only Authority',
  admin: 'Administrator',
}

export const PERMISSION_LABEL = {
  submit_complaint: 'Submit complaints',
  view_own_complaints: 'View own complaints',
  view_assigned_complaints: 'View assigned complaints',
  review_complaints: 'Review complaints',
  reroute_complaints: 'Reroute complaints',
  resolve_complaints: 'Resolve complaints',
  view_scoped_complaints: 'View complaints in scope (read-only)',
  manage_users: 'Manage users',
  manage_rules_and_settings: 'Manage rules and settings',
}

export function homeFor(role) {
  return ROLE_HOME[role] ?? '/login'
}
