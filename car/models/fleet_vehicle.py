from odoo import models, fields, api,_
from odoo.exceptions import ValidationError

class FleetVehicle(models.Model):
    _name = 'fleet.vehicle'
    _description = 'Fleet Vehicle'
    _rec_name = 'display_name'

    name = fields.Char(string='Tên xe', required=True)
    car_company_id =fields.Many2one('car.company' ,string="Tên công ty")
    seat_capacity = fields.Integer(string='Số ghế trên xe', required=True)
    availability_status = fields.Selection([('san_sang', 'Sẵn sàng'),('dang_bao_tri', 'Đang bảo trì')],
                                          default='san_sang', string="Tình trạng xe")
    license_plate = fields.Char(string='Biển số xe',required=True)
    vehicle_type = fields.Selection([('o_to','Ô tô'),('xe_may','Xe máy'),('xe_tai','Xe tải')],default='o_to', string='Loại xe')
    rental_price_per_day = fields.Float(string='Giá thuê xe theo ngày',required=True)
    display_name = fields.Char(string='Tên hiển thị', compute='_compute_display_name', store=True)

    is_active = fields.Boolean(
        string="Công ty đang hoạt động",
        related='car_company_id.is_active',
        store=True,
        readonly=True
    )

    @api.depends('name', 'license_plate', 'seat_capacity')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} - {record.license_plate} ({record.seat_capacity} ghế)"


    @api.constrains('seat_capacity')
    def _seat_capacity(self):
        for rec in self:
            if rec.vehicle_type == "o_to" and (rec.seat_capacity <= 1 or rec.seat_capacity >= 45):
                raise ValidationError("Ô tô có số ghế luôn lớn hơn 1 và nhỏ hơn 45!")
            if rec.vehicle_type == "xe_may" and (rec.seat_capacity <= 0 or rec.seat_capacity > 2) :
                raise ValidationError("Xe máy không thể lớn hơn 2 ghế và nhỏ hơn 1!")
            if rec.vehicle_type == "xe_tai" and (rec.seat_capacity <= 1 or rec.seat_capacity > 4)   :
                raise ValidationError("Xe tải có số ghế luôn lớn hơn 1 và nhỏ hơn 4!")



    @api.constrains('license_plate')
    def _check_unique_license_plate(self):
        for vehicle in self:
            # Kiểm tra xem biển số có tồn tại trong hệ thống không
            existing_vehicle = self.search([
                ('license_plate', '=', vehicle.license_plate),
                ('id', '!=', vehicle.id)  # Tránh kiểm tra chính mình
            ], limit=1)
            if existing_vehicle:
                raise ValidationError("Biển số xe đã tồn tại trong hệ thống!")
            if len(vehicle.license_plate) != 8:
                raise ValidationError("Biển số xe 8 ký tự")


    @api.constrains('rental_price_per_day')
    def _check_rental_price(self):
        for rec in self:
            if rec.rental_price_per_day < 0:
                raise ValidationError("Không thể nhập giá tiền âm!")

    def write(self, vals):
        Booking = self.env['car.booking']
        for vehicle in self:
            # Kiểm tra nếu các field nhạy cảm bị sửa
            fields_being_changed = set(vals.keys())
            restricted_fields = {'name', 'seat_capacity', 'availability_status', 'license_plate', 'vehicle_type',
                                 'rental_price_per_day'}

            if fields_being_changed & restricted_fields:
                if Booking.search_count([
                    ('vehicle_id', '=', vehicle.id),
                    ('state', 'not in', ['hoan_thanh', 'huy'])
                ]) > 0:
                    raise ValidationError(_(
                        "Không thể chỉnh sửa thông tin xe khi xe đang được sử dụng trong đơn đặt chưa hoàn thành hoặc chưa hủy."
                    ))

        return super().write(vals)

    @api.constrains('availability_status', 'car_company_id')
    def _check_not_available_if_company_inactive(self):
        for vehicle in self:
            if vehicle.car_company_id and not vehicle.car_company_id.is_active and vehicle.availability_status == 'san_sang':
                raise ValidationError(_(
                    "Không thể đặt trạng thái xe là 'Sẵn sàng' nếu công ty gắn với xe không hoạt động."
                ))
