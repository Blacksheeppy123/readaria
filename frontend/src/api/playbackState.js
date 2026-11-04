import request from './request'

/**
 * 用户播放状态同步 API
 */

export function getPlaybackState(options = {}) {
  return request({
    url: '/api/v1/playback-state',
    method: 'get',
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

export function updatePlaybackState(state, options = {}) {
  return request({
    url: '/api/v1/playback-state',
    method: 'put',
    data: state,
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}
