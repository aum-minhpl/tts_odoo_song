from odoo import api, fields, models


class ResUsers(models.Model):

    _inherit = 'res.users'

    mode_ids = fields.One2many('res.mode', 'user_id', string="Modes")

    @api.model_create_multi
    def create(self, vals_list):
        records = self.env['res.users']
        for vals in vals_list:
            # Your custom logic using 'vals'
            record = super(ResUsers, self).create(vals)
            records += record
        return records