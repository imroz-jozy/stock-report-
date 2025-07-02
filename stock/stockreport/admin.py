from django.contrib import admin, messages
from django.db.models import Sum
from django.urls import path, reverse
from django.shortcuts import redirect, render
from django.http import HttpResponseRedirect
from .models import master1, tran2, APIConfig
import requests
import xml.etree.ElementTree as ET
from django.utils.html import format_html
import datetime


@admin.register(APIConfig)
class APIConfigAdmin(admin.ModelAdmin):
    list_display = ('url', 'username', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('url', 'username')


@admin.register(master1)
class Master1Admin(admin.ModelAdmin):
    list_display = ('name', 'get_closing_stock')

    def get_closing_stock(self, obj):
        return obj.closing_stock()

    get_closing_stock.short_description = 'Closing Stock'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'import-from-desktop/',
                self.admin_site.admin_view(self.import_from_desktop),
                name='import-from-desktop',
            ),
        ]
        return custom_urls + urls

    def import_from_desktop(self, request):
        # Run import logic on both GET and POST requests
        try:
            # Step 1: Import Master1 data
            master_xml_response = execute_query(query_type='master1')
            if not master_xml_response:
                messages.error(request, "Failed to fetch Master1 data from external source.")
                return HttpResponseRedirect(reverse('admin:stockreport_master1_changelist'))

            master_parsed_data = parse_xml_to_list(master_xml_response, query_type='master1')
            if not master_parsed_data:
                messages.error(request, "No Master1 data found or failed to parse XML response.")
                return HttpResponseRedirect(reverse('admin:stockreport_master1_changelist'))

            old_master1_count = master1.objects.count()
            master1.objects.all().delete()
            messages.info(request, f"Cleared {old_master1_count} master1 records")

            master_imported_count = 0
            for entry in master_parsed_data:
                try:
                    master1.objects.create(
                        code=int(entry['code']),
                        name=entry['name'],
                        mastertype=int(entry['masterType'])
                    )
                    master_imported_count += 1
                except Exception as e:
                    messages.warning(request, f"Error importing master1 record: {str(e)}")

            messages.success(request, f"Successfully imported {master_imported_count} master1 records")

            # Step 2: Import Tran2 data
            xml_response = execute_query(query_type='tran2')
            if not xml_response:
                messages.error(request, "Failed to fetch Tran2 data from external source.")
                return HttpResponseRedirect(reverse('admin:stockreport_master1_changelist'))

            parsed_data = parse_xml_to_list(xml_response, query_type='tran2')
            if not parsed_data:
                messages.error(request, "No Tran2 data found or failed to parse XML response.")
                return HttpResponseRedirect(reverse('admin:stockreport_master1_changelist'))

            old_tran2_count = tran2.objects.count()
            tran2.objects.all().delete()
            messages.info(request, f"Cleared {old_tran2_count} Tran2 records")

            imported_count = 0
            error_count = 0

            for entry in parsed_data:
                try:
                    item = master1.objects.get(code=int(entry['masterCode1']))
                    # Parse date string to date object
                    date_obj = entry['date']
                    if not date_obj or not isinstance(date_obj, str):
                        messages.warning(request, f"Skipped Tran2 record with missing date for vch_no {entry.get('vch_no', 'unknown')}")
                        error_count += 1
                        continue
                    try:
                        # Try date only
                        date_obj = datetime.datetime.strptime(date_obj, "%Y-%m-%d").date()
                    except ValueError:
                        try:
                            # Try ISO format with time
                            date_obj = datetime.datetime.strptime(date_obj, "%Y-%m-%dT%H:%M:%S").date()
                        except ValueError:
                            messages.warning(request, f"Skipped Tran2 record with invalid date '{date_obj}' for vch_no {entry.get('vch_no', 'unknown')}")
                            error_count += 1
                            continue
                    tran2.objects.create(
                        mastercode1=item,
                        Vch_Type=int(entry['Vch_Type']),
                        vch_no=entry['vch_no'],
                        date=date_obj,
                        quantity=float(entry['quantity']),
                        amount=float(entry['amount']),
                    )
                    imported_count += 1
                except Exception as e:
                    error_count += 1
                    messages.warning(request, f"Error importing Tran2 record: {str(e)}")

            messages.success(request, f"Successfully imported {imported_count} Tran2 records")

            if error_count > 0:
                messages.warning(request, f"{error_count} Tran2 records had errors during import.")

        except Exception as e:
            messages.error(request, f"Import failed: {str(e)}")
        return HttpResponseRedirect(reverse('admin:stockreport_master1_changelist'))


def execute_query(query_type='tran2'):
    api_config = APIConfig.get_active_config()
    if not api_config:
        raise ValueError("No active API configuration found")

    queries = {
        'tran2': "SELECT Tran2.MasterCode1, Tran2.VchType, Tran2.VchNo, Tran2.Date, Tran2.Value1, Tran2.Value3 FROM Tran2 INNER JOIN Master1 ON Trim(Tran2.mastercode1) = Trim(Master1.code) WHERE Trim(Master1.mastertype) = '6'",
        'master1': "SELECT Code, MasterType, Name FROM Master1 WHERE MasterType = 6"
    }

    headers = {
        "SC": "1",
        "Qry": queries[query_type],
        "UserName": api_config.username,
        "Pwd": api_config.password
    }

    for method in ['GET', 'POST']:
        try:
            response = requests.get(api_config.url, headers=headers) if method == 'GET' else requests.post(api_config.url, headers=headers)
            if response.status_code == 200:
                return response.text
        except requests.RequestException:
            continue

    return None


def parse_xml_to_list(xml_data, query_type='tran2'):
    try:
        namespaces = {'z': '#RowsetSchema'}
        root = ET.fromstring(xml_data)
        result = []

        for row in root.findall(".//z:row", namespaces=namespaces):
            if query_type == 'tran2':
                entry = {
                    "masterCode1": row.attrib.get("MasterCode1", ""),
                    "Vch_Type": row.attrib.get("VchType", ""),
                    "vch_no": row.attrib.get("VchNo", ""),
                    "date": row.attrib.get("Date", ""),
                    "quantity": float(row.attrib.get("Value1", 0)) if row.attrib.get("Value1") else 0,
                    "amount": float(row.attrib.get("Value3", 0)) if row.attrib.get("Value3") else 0
                }
            else:
                entry = {
                    "code": row.attrib.get("Code", ""),
                    "masterType": row.attrib.get("MasterType", ""),
                    "name": row.attrib.get("Name", "")
                }
            result.append(entry)

        return result

    except ET.ParseError:
        return []


@admin.register(tran2)
class Tran2Admin(admin.ModelAdmin):
    list_display = ('vch_no', 'date')
