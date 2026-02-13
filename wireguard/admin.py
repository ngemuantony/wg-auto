from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import WireGuardPeer, SMTPSettings, WireGuardServer


@admin.register(WireGuardServer)
class WireGuardServerAdmin(admin.ModelAdmin):
    list_display = ("name", "endpoint", "interface",'uplink_interface', "port", "is_active", "has_keys", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "endpoint")
    readonly_fields = ("public_key_display", "private_key_display", "created_at", "updated_at", "regenerate_keys_button")
    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "endpoint", "is_active")
        }),
        ("Network Configuration", {
            "fields": ("interface", "port", "server_address", "mtu")
        }),
        ("Keys", {
            "fields": ("public_key_display", "private_key_display", "regenerate_keys_button"),
            "classes": ("collapse",),
            "description": "Keys are auto-generated on creation. Click regenerate to create new keys."
        }),
        ("Client Defaults", {
            "fields": ("dns", "allowed_ips", "persistent_keepalive")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing server
            return self.readonly_fields + ("interface", "port", "server_address")
        return self.readonly_fields

    def has_keys(self, obj):
        """Display indicator of whether keys are present"""
        if obj.private_key_encrypted and obj.private_key_encrypted != "-" and len(obj.private_key_encrypted) > 10:
            return mark_safe('<span style="color: green;">✓ Present</span>')
        return mark_safe('<span style="color: red;">✗ Missing</span>')
    has_keys.short_description = "Keys Status"

    def public_key_display(self, obj):
        """Display the public key with copy capability"""
        if not obj or not obj.pk:
            return mark_safe('<em style="color: orange;">Not generated yet (will be created on save)</em>')
        if not obj.public_key or obj.public_key == "-":
            return mark_safe('<em style="color: orange;">Not generated yet</em>')
        return format_html(
            '<code style="word-break: break-all; display: block; padding: 10px; background: #f5f5f5; border-radius: 4px;">{}</code>',
            obj.public_key
        )
    public_key_display.short_description = "Server Public Key"

    def private_key_display(self, obj):
        """Display private key status (encrypted, not the actual value)"""
        if not obj or not obj.pk:
            return mark_safe('<em style="color: orange;">Not generated yet (will be created on save)</em>')
        if not obj.private_key_encrypted or obj.private_key_encrypted == "-":
            return mark_safe('<em style="color: orange;">Not generated yet</em>')
        return format_html(
            '<div style="padding: 10px; background: #fff3cd; border-radius: 4px; color: #856404;">'
            '<strong>Status:</strong> Encrypted and stored securely<br>'
            '<strong>Length:</strong> {} characters<br>'
            '<em>Private key is never displayed for security reasons. Use the API or export function to retrieve it.</em>'
            '</div>',
            len(obj.private_key_encrypted)
        )
    private_key_display.short_description = "Server Private Key (Encrypted)"

    def regenerate_keys_button(self, obj):
        """Display information about key regeneration"""
        if not obj or not obj.pk:
            return mark_safe('<em>Keys will be auto-generated when you save this server.</em>')
        return format_html(
            '<div style="padding: 10px; background: #e7f3ff; border-radius: 4px; border-left: 4px solid #2196F3; color: #0c5460;">'
            '<strong>To regenerate keys:</strong><br>'
            '1. Save the server (this will auto-generate missing keys)<br>'
            '2. Or use the management command: '
            '<code>python manage.py regenerate_server_keys {}</code>'
            '</div>',
            obj.pk
        )
    regenerate_keys_button.short_description = "Key Management"

    def save_model(self, request, obj, form, change):
        """Save model and log key generation"""
        super().save_model(request, obj, form, change)
        if obj.private_key_encrypted and obj.private_key_encrypted != "-":
            self.message_user(request, "Server saved successfully. Keys are auto-generated if missing.")
        else:
            self.message_user(request, "Server saved. Please refresh to see generated keys.", level="warning")


@admin.register(WireGuardPeer)
class PeerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "allowed_ip", "is_active", "platform", "get_server_name", "updated_at")
    list_filter = ("is_active", "platform", "server", "created_at")
    search_fields = ("name", "email", "allowed_ip")
    readonly_fields = ("public_key", "private_key_encrypted", "created_at", "updated_at")
    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "email", "platform", "server")
        }),
        ("Network Configuration", {
            "fields": ("allowed_ip", "allowed_ips", "dns", "server_endpoint")
        }),
        ("Keys", {
            "fields": ("public_key", "private_key_encrypted"),
            "classes": ("collapse",)
        }),
        ("Configuration", {
            "fields": ("qr_path",),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def get_server_name(self, obj):
        if obj.server:
            return obj.server.name
        server = obj.get_server()
        return f"{server.name} (default)" if server else "No server"
    get_server_name.short_description = "Server"

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing existing peer
            return self.readonly_fields + ("created_at",)
        return self.readonly_fields


admin.site.register(SMTPSettings)
