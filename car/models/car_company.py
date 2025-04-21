from odoo import api , fields, models
from odoo.exceptions import ValidationError


class CarCompany(models.Model):
    _name="car.company"
    _description = "Car Company"

    name = fields.Char(string="Tên công ty" ,required=True)
    fax = fields.Char(string="Mã số thuế" ,required=True)
    address= fields.Char(string="Địa chỉ" ,required=True)
    primary_contact_person = fields.Char(string="Người liên hệ chính",required=True)
    is_active = fields.Boolean(string="Đang hoạt động", default=True)
    fleet_vehicle_ids = fields.One2many("fleet.vehicle" , "car_company_id",string="Danh sách xe")

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            domain = [('name', '=', record.name)]
            if record.id:
                domain.append(('id', '!=', record.id))
            existing = self.search_count(domain)
            if existing:
                raise ValidationError("Tên đã tồn tại. Vui lòng nhập tên khác.")

    @api.constrains('fax')
    def _check_fax(self):
        for record in self:
            # Kiểm tra trùng mã số thuế
            domain = [('fax', '=', record.fax)]
            if record.id:
                domain.append(('id', '!=', record.id))
            existing = self.search_count(domain)
            if existing:
                raise ValidationError("Mã số thuế đã tồn tại. Vui lòng nhập mã khác.")