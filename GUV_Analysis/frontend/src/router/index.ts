import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/pages/Dashboard.vue'
import TaskCreate from '@/pages/TaskCreate.vue'
import TaskList from '@/pages/TaskList.vue'
import TaskParams from '@/pages/TaskParams.vue'
import TaskQueue from '@/pages/TaskQueue.vue'
import SystemInfo from '@/pages/SystemInfo.vue'
import Login from '@/pages/Login.vue'
import Users from '@/pages/Users.vue'
import SystemConfig from '@/pages/SystemConfig.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard,
  },
  {
    path: '/tasks/queue',
    name: 'TaskQueue',
    component: TaskQueue,
  },
  {
    path: '/tasks/create',
    name: 'TaskCreate',
    component: TaskCreate,
  },
  {
    path: '/tasks',
    name: 'TaskList',
    component: TaskList,
  },
  {
    path: '/tasks/:id',
    name: 'TaskParams',
    component: TaskParams,
  },
  {
    path: '/system',
    name: 'SystemInfo',
    component: SystemInfo,
  },
  {
    path: '/system/config',
    name: 'SystemConfig',
    component: SystemConfig,
  },
  {
    path: '/users',
    name: 'Users',
    component: Users,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = sessionStorage.getItem('token')
  if (!to.meta.public && !token) {
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router
