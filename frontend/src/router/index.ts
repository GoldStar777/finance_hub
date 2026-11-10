import { createRouter, createWebHistory } from 'vue-router';
import DashboardView from '../views/DashboardView.vue';
import LedgerView from '../views/LedgerView.vue';
import StagingView from '../views/StagingView.vue';
import PortfoliosView from '../views/PortfoliosView.vue';
import AnalysisView from '../views/AnalysisView.vue';
import DataQualityView from '../views/DataQualityView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
    {
      path: '/portfolios',
      name: 'portfolios',
      component: PortfoliosView,
    },
    {
      path: '/analysis',
      name: 'analysis',
      component: AnalysisView,
    },
    {
      path: '/cashflow',
      redirect: '/analysis?section=spending'
    },
    {
      path: '/spending',
      redirect: '/analysis?section=spending'
    },
    {
      path: '/ledger',
      name: 'ledger',
      component: LedgerView,
    },
    {
      path: '/queue',
      name: 'queue',
      component: StagingView,
    },
    {
      path: '/staging',
      redirect: '/queue'
    },
    {
      path: '/review',
      name: 'review',
      component: DataQualityView,
    },
    {
      path: '/data-quality',
      redirect: '/review'
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ],
});

export default router;

