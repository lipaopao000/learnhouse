'use strict';
(async()=>{
 try{const response=await fetch('/api/v1/orgs/slug/default',{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;const org=await response.json();document.querySelectorAll('[data-org-name]').forEach(e=>e.textContent=org.name);if(org.org_uuid&&org.logo_image){const src='/content/orgs/'+encodeURIComponent(org.org_uuid)+'/logos/'+encodeURIComponent(org.logo_image);document.querySelectorAll('[data-org-logo]').forEach(e=>{e.src=src;e.alt=org.name;});}}catch{}
 if(document.body.dataset.page==='admin')try{const response=await fetch('/api/v1/users/profile',{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;const user=await response.json();document.querySelectorAll('[data-current-name]').forEach(e=>e.textContent=user.first_name||user.username);}catch{}
})();
