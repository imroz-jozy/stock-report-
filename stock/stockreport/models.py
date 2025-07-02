from django.db import models
from django.db.models import Sum


class APIConfig(models.Model):
    url = models.URLField(max_length=200, help_text="API endpoint URL")
    username = models.CharField(max_length=100, help_text="API username")
    password = models.CharField(max_length=100, help_text="API password")
    is_active = models.BooleanField(default=True, help_text="Only one configuration can be active at a time")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "API Configuration"
        verbose_name_plural = "API Configurations"

    def save(self, *args, **kwargs):
        if self.is_active:
            # Set all other configurations to inactive
            APIConfig.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_config(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"API Config ({self.url})"

# Create your models here.
class master1(models.Model):
    name = models.CharField(max_length=100, verbose_name="Name")
    code = models.IntegerField(verbose_name="Code")
    mastertype = models.IntegerField(verbose_name="MasterType")

    class Meta:
        verbose_name = "Master"
        verbose_name_plural = "Masters"

    def __str__(self):
        return self.name
    
    def closing_stock(self):
        """Calculate closing stock for this master item"""
        total_quantity = self.tran2_set.aggregate(Sum('quantity'))['quantity__sum']
        return total_quantity if total_quantity is not None else 0
    
    @classmethod
    def get_masters_with_closing_stock(cls):
        """Get all masters with their closing stock calculated"""
        masters = cls.objects.all()
        for master in masters:
            master.closing_stock_value = master.closing_stock()
        return masters


class tran2(models.Model):
    mastercode1 = models.ForeignKey(master1, on_delete=models.CASCADE, verbose_name="Master Code")
    Vch_Type=models.IntegerField(verbose_name="Voucher Type")
    date= models.DateField(verbose_name="Date")
    vch_no = models.CharField(max_length=50, verbose_name="Voucher No")
    quantity = models.FloatField(verbose_name="Quantity")
    amount = models.FloatField(verbose_name="Amount")
    
    def __str__(self):
        return f'{str(self.vch_no)}- {str(self.mastercode1.name)}'
    
