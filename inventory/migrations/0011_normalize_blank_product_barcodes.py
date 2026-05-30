from django.db import migrations


def normalize_blank_barcodes(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    Product.objects.filter(barcode='').update(barcode=None)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_product_barcode'),
    ]

    operations = [
        migrations.RunPython(normalize_blank_barcodes, migrations.RunPython.noop),
    ]
