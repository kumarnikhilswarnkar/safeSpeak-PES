// The signed-in user's own profile. There is no user ID anywhere: the server
// always acts on the account in the token.
export const getProfile = (authRequest) => authRequest('/profile')
export const updateProfile = (authRequest, changes) => authRequest('/profile', { method: 'PATCH', body: changes })
export const uploadPhoto = (authRequest, file) => authRequest('/profile/photo', { method: 'PUT', rawBody: file })
export const deletePhoto = (authRequest) => authRequest('/profile/photo', { method: 'DELETE' })
export const getPhoto = (authRequest) => authRequest('/profile/photo', { responseType: 'blob' })
