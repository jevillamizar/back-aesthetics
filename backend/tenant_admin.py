"""
Custom admin site that filters models based on tenant context
"""
from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class TenantAdminSite(admin.AdminSite):
    """
    Custom admin site that filters registered models based on schema
    """
    
    def get_app_list(self, request, app_label=None):
        """
        Filter app list based on current schema
        """
        from django.db import connection
        
        app_list = super().get_app_list(request, app_label)
        
        # Models that should only appear in public schema
        public_only_models = {'clinic', 'domain'}
        
        # Models that should only appear in tenant schemas
        tenant_only_models = {
            'appointment', 'cliniclanding', 'medicalrecord', 
            'medicalrecordtreatment', 'patient', 'treatment'
        }
        
        schema = connection.schema_name
        
        filtered_app_list = []
        for app in app_list:
            filtered_models = []
            for model in app.get('models', []):
                model_name = model.get('object_name', '').lower()
                
                # Filter based on schema
                if schema == 'public':
                    # In public schema, only show public models
                    if model_name not in tenant_only_models:
                        filtered_models.append(model)
                else:
                    # In tenant schemas, only show tenant models
                    if model_name not in public_only_models:
                        filtered_models.append(model)
            
            # Only include app if it has models after filtering
            if filtered_models:
                app['models'] = filtered_models
                filtered_app_list.append(app)
        
        return filtered_app_list


class TenantAdminConfig(AdminConfig):
    """
    Custom admin config to use TenantAdminSite
    """
    default_site = 'backend.tenant_admin.TenantAdminSite'
