from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarBooking(models.Model):
    _name = 'car.booking'
    _description = 'Car Booking'
    _order = 'booking_date desc'

    name = fields.Char(string='Mã tham chiếu đơn đặt xe', readonly=True, copy=False)

    def _partner_ids_domain_customer(self):
        if self.env.user.has_group('car.group_admin'):
            partners = self.env['res.mode'].search([('role', '=', 'customer')])
            return [('id', 'in', partners.ids)]
        elif self.env.user.has_group('car.group_customer'):
            # Tìm tất cả bản ghi res.mode của user hiện tại với role='customer'
            partners = self.env['res.mode'].search([
                ('user_id', '=', self.env.user.id),
                ('role', '=', 'customer')
            ])
            return [('id', 'in', partners.ids)]
        return [('id', 'in', [])]

    def _partner_ids_domain_driver(self):
        if self.env.user.has_group('car.group_admin'):
            # Admin có thể chọn tất cả tài xế online
            partners = self.env['res.mode'].search([
                ('role', '=', 'driver'),
                ('driver_status', '=', 'online')
            ])
            return [('id', 'in', partners.ids)]

        elif self.env.user.has_group('car.group_customer'):
            # Khách hàng chỉ thấy tài xế online
            partners = self.env['res.mode'].search([
                ('role', '=', 'driver'),
                ('driver_status', '=', 'online')
            ])
            return [('id', 'in', partners.ids)]

        # Trả về danh sách rỗng nếu người dùng không thuộc nhóm nào
        return [('id', 'in', [])]

    customer_id = fields.Many2one('res.mode', string='Khách hàng đặt xe', domain=_partner_ids_domain_customer,
                                  required=True)
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Xe',
        required=True,
        help="Chọn xe để đặt"
    )
    # Thêm trường liên kết đến công ty xe (tự động lấy từ xe)
    company_id = fields.Many2one(
        'car.company',
        string='Công ty xe',
        related='vehicle_id.car_company_id',
        store=True,
        readonly=True,
        help="Công ty sở hữu xe"
    )
    driver_id = fields.Many2one('res.mode', string='Tài xế nhận chuyến xe', domain=_partner_ids_domain_driver,
                                required=True)
    booking_date = fields.Datetime(string='Ngày đặt xe', required=True, default=fields.Datetime.now)
    pickup_date = fields.Datetime(string='Ngày nhận xe', required=True)
    return_date = fields.Datetime(string='Ngày trả xe', required=True)
    total_price = fields.Float(string='Tổng giá thuê xe', compute='_compute_total_price', readonly=True, store=True)
    # Thêm trường amount để dùng cho báo cáo doanh thu
    amount = fields.Float(string='Doanh thu', related='total_price', store=True, readonly=True)
    state = fields.Selection([
        ('nhap', 'Nháp'),
        ('xac_nhan', 'Xác nhận'),
        ('dang_thuc_hien', 'Đang thực hiện'),
        ('hoan_thanh', 'Hoàn thành'),
        ('huy', 'Hủy')
    ], string='Trạng thái đặt xe', default='nhap')


    @api.constrains('customer_id')
    def _check_customer_role(self):
        for record in self:
            if record.customer_id and record.customer_id.role != 'customer':
                raise ValidationError("Người được chọn không có vai trò là 'customer'.")

    @api.constrains('driver_id')
    def _check_driver_role(self):
        for record in self:
            if record.driver_id and record.driver_id.role != 'driver':
                raise ValidationError("Người được chọn không có vai trò là 'driver'.")

    # TU DONG TANG REF
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('car.booking') or _('New')
        return super().create(vals_list)

    # NGAY TRA XE PHAI LON HON NGAY NHAN XE
    @api.constrains('pickup_date', 'return_date')
    def _check_dates(self):
        for rec in self:
            if rec.return_date <= rec.pickup_date:
                raise ValidationError(_('Ngày trả xe phải sau ngày nhận xe.'))

    # KHONG THE SUA THONG TIN KHI DON HANG DA HOAN THANH
    @api.constrains('customer_id', 'vehicle_id', 'driver_id', 'pickup_date', 'return_date')
    def _check_if_completed(self):
        for record in self:
            if record.state == 'hoan_thanh':
                raise ValidationError("Không thể sửa thông tin khi đơn đã hoàn thành.")

    # TINH TONG SO TIEN PHAI TRA
    @api.depends('pickup_date', 'return_date', 'vehicle_id.rental_price_per_day')
    def _compute_total_price(self):
        for rec in self:
            if rec.pickup_date and rec.return_date and rec.return_date > rec.pickup_date:
                rental_price_per_day = rec.vehicle_id.rental_price_per_day or 0
                days = (rec.return_date - rec.pickup_date).days or 1
                # Đảm bảo ít nhất 1 ngày
                rec.total_price = days * rental_price_per_day
            else:
                rec.total_price = 0

    @api.constrains('pickup_date', 'return_date', 'vehicle_id', 'driver_id', 'state')
    def _check_vehicle_and_driver_overlap(self):
        for rec in self:
            if rec.state not in ['xac_nhan', 'dang_thuc_hien']:
                continue

            domain = [
                ('id', '!=', rec.id),
                ('pickup_date', '<', rec.return_date),
                ('return_date', '>', rec.pickup_date),
                ('state', 'in', ['xac_nhan', 'dang_thuc_hien']),
            ]

            # Kiểm tra trùng xe
            if rec.vehicle_id:
                overlapping_vehicle = self.env['car.booking'].sudo().search(domain + [
                    ('vehicle_id', '=', rec.vehicle_id.id)
                ], limit=1)
                if overlapping_vehicle:
                    raise ValidationError(_("Xe đã được đặt trong khoảng thời gian này."))

            # Kiểm tra trùng tài xế
            if rec.driver_id:
                overlapping_driver = self.env['car.booking'].sudo().search(domain + [
                    ('driver_id', '=', rec.driver_id.id)
                ], limit=1)
                if overlapping_driver:
                    raise ValidationError(_("Tài xế đã được đặt trong khoảng thời gian này."))

    # Button

    def action_nhap(self):
        for rec in self:
            if rec.state != 'nhap':
                raise ValidationError(_("Trạng thái không thể chuyển trực tiếp từ '%s' đến 'Nháp'." % rec.state))
            rec.state = 'nhap'

    def action_xac_nhan(self):
        for rec in self:
            if rec.state != 'nhap':
                raise ValidationError(_("Chỉ có thể xác nhận từ trạng thái 'Nháp'."))
            rec.state = 'xac_nhan'

    def action_dang_thuc_hien(self):
        for rec in self:
            if rec.state != 'xac_nhan':
                raise ValidationError(_("Trạng thái chỉ có thể chuyển từ 'Xác nhận' đến 'Đang thực hiện'."))
            rec.state = 'dang_thuc_hien'

    def action_hoan_thanh(self):
        for rec in self:
            if rec.state != 'dang_thuc_hien':
                raise ValidationError(_("Trạng thái chỉ có thể chuyển từ 'Đang thực hiện' đến 'Hoàn thành'."))
            rec.state = 'hoan_thanh'

    def action_huy(self):
        for rec in self:
            if rec.state == 'hoan_thanh':
                raise ValidationError(_("Không thể hủy đơn khi đơn đã hoàn thành."))
            rec.state = 'nhap'

    @api.constrains('pickup_date', 'return_date', 'customer_id')
    def _check_time_overlap_for_customer(self):
        for record in self:
            overlapping_bookings = self.sudo().search([
                ('customer_id', '=', record.customer_id.id),
                ('id', '!=', record.id),
                ('pickup_date', '<', record.return_date),
                ('return_date', '>', record.pickup_date),
                ('state', 'in', ['xac_nhan', 'dang_thuc_hien']),  # Chỉ kiểm tra đơn đang hoạt động
            ])
            if overlapping_bookings:
                raise ValidationError("Bạn đã có đơn đặt xe khác trùng thời gian.")

    @api.model
    def get_bookings_by_month(self):
        domain = [('state', '=', 'hoan_thanh')]
        bookings = self.read_group(
            domain=domain,
            fields=['id'],
            groupby=['pickup_date:month'],
            orderby='pickup_date'
        )

        result = []
        for b in bookings:
            month_field = b.get('pickup_date:month')
            if month_field:
                month = fields.Date.to_string(month_field)[:7]  # YYYY-MM
                result.append({
                    'month': month,
                    'count': b.get('__count', 0)
                })
        return result

    @api.model
    def get_most_booked_vehicles(self, limit=5):
        domain = [('state', '=', 'hoan_thanh')]
        bookings = self.read_group(
            domain=domain,
            fields=['vehicle_id'],
            groupby=['vehicle_id'],
            orderby='__count desc',
            limit=limit
        )

        result = []
        for b in bookings:
            vehicle_data = b.get('vehicle_id')
            if vehicle_data:
                vehicle = self.env['fleet.vehicle'].browse(vehicle_data[0])
                result.append({
                    'vehicle': vehicle.name,
                    'count': b.get('__count', 0)
                })
        return result

    @api.model
    def get_top_customers(self, limit=5):
        domain = [('state', '=', 'hoan_thanh')]
        bookings = self.read_group(
            domain=domain,
            fields=['customer_id'],
            groupby=['customer_id'],
            orderby='__count desc',
            limit=limit
        )

        result = []
        for b in bookings:
            customer_data = b.get('customer_id')
            if customer_data:
                customer = self.env['res.mode'].browse(customer_data[0])
                result.append({
                    'customer': customer.name,
                    'count': b.get('__count', 0)
                })
        return result

    # Thêm phương thức mới để báo cáo theo công ty
    @api.model
    def get_bookings_by_company(self, start_date=None, end_date=None):
        domain = [('state', '=', 'hoan_thanh')]

        # Thêm điều kiện lọc theo khoảng thời gian nếu có
        if start_date:
            domain.append(('pickup_date', '>=', start_date))
        if end_date:
            domain.append(('pickup_date', '<=', end_date))

        bookings = self.read_group(
            domain=domain,
            fields=['amount', 'id'],
            groupby=['company_id'],
            orderby='company_id'
        )

        result = []
        for b in bookings:
            company_data = b.get('company_id')
            if company_data:
                company = self.env['car.company'].browse(company_data[0])
                result.append({
                    'company': company.name,
                    'booking_count': b.get('__count', 0),
                    'total_amount': b.get('amount', 0)
                })
        return result


    @api.constrains('vehicle_id')
    def _check_vehicle_company_active(self):
        for rec in self:
            company = rec.vehicle_id.car_company_id
            if company and not company.is_active:
                raise ValidationError(
                    "Không thể đặt xe thuộc công ty đang ngưng hoạt động."
                )

    def write(self, vals):
        for record in self:
            # Nếu chỉ update trạng thái thì cho phép
            if set(vals.keys()) == {'state'}:
                continue

            if record.state in ['xac_nhan', 'dang_thuc_hien', 'hoan_thanh']:
                raise ValidationError(_(
                    "Không thể chỉnh sửa đơn đặt xe khi đơn đang ở trạng thái '%s'."
                ) % dict(self.fields_get(['state'])['state']['selection']).get(record.state))

        return super().write(vals)