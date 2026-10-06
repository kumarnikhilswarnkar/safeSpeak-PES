// Dashboards, notifications, evaluation report and automation status.

export const getOverview = (authRequest) => authRequest('/analytics/overview')
export const getNotifications = (authRequest) => authRequest('/notifications')
export const getEvaluation = (authRequest) => authRequest('/research/evaluation')
export const getAutomation = (authRequest) => authRequest('/system/automation')
export const runAutomationNow = (authRequest) => authRequest('/system/automation/run', { method: 'POST' })
