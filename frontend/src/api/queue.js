import request from './request'

/**
 * 用户听读队列同步 API
 */

export function getUserQueue(options = {}) {
  return request({
    url: '/api/v1/queue',
    method: 'get',
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

export function updateUserQueue(items, options = {}) {
  return request({
    url: '/api/v1/queue',
    method: 'put',
    data: { items },
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}

export function clearUserQueue(options = {}) {
  return request({
    url: '/api/v1/queue',
    method: 'delete',
    silent: true,
    headers: { 'X-Silent': '1' }
  })
}
