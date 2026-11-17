import { createRouter, createWebHistory } from 'vue-router'
import CampaignList from '@/views/CampaignList.vue'
import CampaignForm from '@/views/CampaignForm.vue'
import CampaignCreator from '@/views/CampaignCreator.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/campaigns' },
    { path: '/campaigns', name: 'campaigns', component: CampaignList },
    { path: '/create', name: 'creator', component: CampaignCreator },
    {
      path: '/campaigns/:id/edit',
      name: 'campaign-edit',
      component: CampaignForm,
      props: (route) => ({ id: Number(route.params.id) }),
    },
  ],
})
