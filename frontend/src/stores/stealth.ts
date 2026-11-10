import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useStealthStore = defineStore('stealth', () => {
  const isStealth = ref(localStorage.getItem('stealth') === '1');

  function initStealth() {
    if (isStealth.value) {
      document.body.classList.add('stealth');
    } else {
      document.body.classList.remove('stealth');
    }
  }

  function toggleStealth() {
    isStealth.value = !isStealth.value;
    if (isStealth.value) {
      document.body.classList.add('stealth');
      localStorage.setItem('stealth', '1');
    } else {
      document.body.classList.remove('stealth');
      localStorage.setItem('stealth', '0');
    }
  }

  return { isStealth, initStealth, toggleStealth };
});

