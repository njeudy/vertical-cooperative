# -*- coding: utf-8 -*-
import base64
from datetime import datetime
import re

import werkzeug
import werkzeug.urls

from openerp import http, SUPERUSER_ID
from openerp.http import request
from openerp.tools.translate import _

_TECHNICAL = ['view_from', 'view_callback']  # Only use for behavior, don't stock it
_BLACKLIST = ['id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'user_id', 'active']  # Allow in description
        
class WebsiteSubscription(http.Controller):

    @http.route(['/page/become_cooperator','/become_cooperator'], type='http', auth="public", website=True)
    def display_become_cooperator_page(self, **kwargs):
        values = {}
        if request.env.user.login != 'public':
            partner = request.env.user.partner_id
            if partner.is_company:
                return request.website.render("easy_my_coop.becomecompanycooperator", values)
        values = self.fill_values(values,False,True)
        
        for field in ['email','firstname','lastname','birthdate','iban','share_product_id','no_registre','address','city','zip_code','country_id','phone','lang','nb_parts','total_parts','error_msg']:
            if kwargs.get(field):
                values[field] = kwargs.pop(field)
        
        values.update(kwargs=kwargs.items())
        return request.website.render("easy_my_coop.becomecooperator", values)
    
    @http.route(['/page/become_company_cooperator','/become_company_cooperator'], type='http', auth="public", website=True)
    def display_become_company_cooperator_page(self, **kwargs):
        values = {}

        values = self.fill_values(values,True,True)
        
        for field in ['is_company','company_register_number','company_name','company_email','company_type','email','firstname','lastname','birthdate','iban','share_product_id','no_registre','address','city','zip_code','country_id','phone','lang','nb_parts','total_parts','error_msg']:
            if kwargs.get(field):
                values[field] = kwargs.pop(field)
        values.update(kwargs=kwargs.items())
        return request.website.render("easy_my_coop.becomecompanycooperator", values)
    
    def preRenderThanks(self, values, kwargs):
        """ Allow to be overrided """
        return {
            '_values': values,
            '_kwargs': kwargs,
        }

    def get_subscription_response(self, values, kwargs):
        values = self.preRenderThanks(values, kwargs)
        return request.website.render(kwargs.get("view_callback", "easy_my_coop.cooperator_thanks"), values)
    
    def get_date_string(self,birthdate):
        if birthdate:
            birthdate = datetime.strptime(birthdate,"%Y-%m-%d") 
            return datetime.strftime(birthdate,"%d/%m/%Y")
        return False

    def get_values_from_user(self, values, is_company):
        # the subscriber is connected
        if request.env.user.login != 'public':
            values['logged'] = 'on'
            partner = request.env.user.partner_id
            
            if partner.member or partner.old_member:
                values['already_cooperator'] = 'on'
            if partner.bank_ids:
                values['iban'] = partner.bank_ids[0].acc_number
            values['address'] = partner.street
            values['zip_code'] = partner.zip
            values['city'] = partner.city
            values['country_id'] = partner.country_id.id
            
            if is_company:
                #company values
                values['company_register_number'] = partner.company_register_number
                values['company_name'] = partner.name
                values['company_email'] = partner.email
                #contact person values
                representative = partner.get_representative()
                values['firstname'] = representative.firstname
                values['lastname'] = representative.lastname
                values['gender'] = representative.gender
                values['email'] = representative.email
                values['contact_person_function'] = representative.function
                values['no_registre'] = representative.national_register_number
                values['birthdate'] = self.get_date_string(representative.birthdate)
                values['lang'] = representative.lang
                values['phone'] = representative.phone
            else:
                values['firstname'] = partner.firstname
                values['lastname'] = partner.lastname
                values['email'] = partner.email
                values['gender'] = partner.gender
                values['no_registre'] = partner.national_register_number
                values['birthdate'] = self.get_date_string(partner.birthdate)
                values['lang'] = partner.lang
                values['phone'] = partner.phone
        return values
    
    def fill_values(self, values, is_company, load_from_user=False):
        company = request.website.company_id
        if load_from_user:
            values = self.get_values_from_user(values,is_company)
        values['countries'] = self.get_countries()
        values['langs'] = self.get_langs()
        values['products'] = self.get_products_share(is_company)
        fields_desc = request.env['subscription.request'].sudo().fields_get(['company_type','gender'])
        values['company_types'] = fields_desc['company_type']['selection']
        values['genders'] = fields_desc['gender']['selection']
        
        if not values.get('share_product_id'):
            products = request.env['product.template'].sudo().get_web_share_products(is_company)
            for product in products:
                if product.default_share_product == True:
                    values['share_product_id'] = product.id
                    break
        if not values.get('country_id'):
            if company.default_country_id:
                values['country_id'] = company.default_country_id.id
            else:
                values['country_id'] = '21'    
        if not values.get('activities_country_id'):
            if company.default_country_id:
                values['activities_country_id'] = company.default_country_id.id
            else:
                values['activities_country_id'] = '21'
        if not values.get('lang'):
            if company.default_lang_id:
                values['lang'] = company.default_lang_id.code
        return values 
    
    def get_products_share(self, is_company):
        products = request.env['product.template'].sudo().get_web_share_products(is_company)
        
        return products
    
    def get_countries(self):
        countries = request.env['res.country'].sudo().search([])
        
        return countries
    
    def get_langs(self):
        langs = request.env['res.lang'].sudo().search([])
        return langs    
    
    @http.route(['/subscription/get_share_product'], type='json', auth="public", methods=['POST'], website=True)
    def get_share_product(self, share_product_id, **kw):
        product = request.env['product.template'].sudo().browse(int(share_product_id))
        return {product.id: {'list_price':product.list_price,'min_qty':product.minimum_quantity,'force_min_qty':product.force_min_qty}}
    
    @http.route(['/subscription/subscribe_share'], type='http', auth="public", website=True)
    def share_subscription(self, **kwargs):
        user_obj = request.env['res.users']
        post_file = []  # List of file to add to ir_attachment once we have the ID
        post_description = []  # Info to add after the message
        values = {}
 
        for field_name, field_value in kwargs.items():
            if hasattr(field_value, 'filename'):
                post_file.append(field_value)
            elif field_name in request.registry['subscription.request']._fields and field_name not in _BLACKLIST:
                values[field_name] = field_value
            elif field_name not in _TECHNICAL:  # allow to add some free fields or blacklisted field like ID
                post_description.append("%s: %s" % (field_name, field_value))
        
        logged = kwargs.get("logged")=='on'
        if logged:
            partner = request.env.user.partner_id
            values['partner_id'] = partner.id
            values['already_cooperator'] = partner.member
 
        is_company = False
        if kwargs.get("is_company") == 'on':
            is_company = True
        values["is_company"] = is_company
        
        redirect = "easy_my_coop.becomecooperator"
        if is_company:
           redirect = "easy_my_coop.becomecompanycooperator"
               
        if not kwargs.has_key('g-recaptcha-response') or not request.website.is_captcha_valid(kwargs['g-recaptcha-response']):
           values = self.fill_values(values,is_company)
           values["error_msg"] = "the captcha has not been validated, please fill in the captcha"
           
           return request.website.render(kwargs.get("view_from", redirect), values)
        
        if not logged and kwargs.has_key('email'):
           user = user_obj.sudo().search([('login','=',kwargs.get("email"))])
           if user:
               values = self.fill_values(values,is_company)
               values.update(kwargs)
               values["error_msg"] = "There is an existing account for this mail address. Please login before fill in the form"
               
               return request.website.render(redirect, values)
           
        # fields validation : Check that required field from model subscription_request exists
        required_fields = request.env['subscription.request'].sudo().get_required_field() 
        error = set(field for field in required_fields if not values.get(field))

        if error:
            values = self.fill_values(values, is_company)
            values["error_msg"] = "Some mandatory fields have not been filled"
            values = dict(values, error=error, kwargs=kwargs.items())
            return request.website.render(kwargs.get("view_from", redirect), values)
        
        if kwargs.get("already_cooperator") == 'on':
            already_cooperator = True
        
        lastname = kwargs.get("lastname").upper()
        firstname = kwargs.get("firstname").title()
            
        values["name"] = firstname + " " + lastname
        values["lastname"] = lastname
        values["firstname"] = firstname
        values["birthdate"] = datetime.strptime(kwargs.get("birthdate"), "%d/%m/%Y").date()
        values["source"] = "website"
        
        if kwargs.get("share_product_id"):
            product_id = kwargs.get("share_product_id")
            product = request.env['product.template'].sudo().browse(int(product_id)).product_variant_ids[0]
            values["share_product_id"] = product.id
        
        #check the subscription's amount  
        company = request.website.company_id
        max_amount = company.subscription_maximum_amount
        total_amount = float(kwargs.get('total_parts'))
        
        if max_amount > 0 and total_amount > max_amount:
           values = self.fill_values(values,is_company)
           values["error_msg"] = "You can't subscribe for an amount that exceed " + str(max_amount) + company.currency_id.symbol
           return request.website.render("easy_my_coop.becomecooperator", values)
        
        if is_company:
            if kwargs.get("company_register_number", is_company):
                values["company_register_number"] = re.sub('[^0-9a-zA-Z]+', '', kwargs.get("company_register_number"))
            subscription_id = request.env['subscription.request'].sudo().create_comp_sub_req(values)
        else:
            if kwargs.get("no_registre"):
                values["no_registre"] = re.sub('[^0-9a-zA-Z]+', '', kwargs.get("no_registre"))
            subscription_id = request.env['subscription.request'].sudo().create(values)
        
        values.update(subscription_id = subscription_id)
        
        if subscription_id:
            for field_value in post_file:
                attachment_value = {
                    'name': field_value.filename,
                    'res_name': field_value.filename,
                    'res_model': 'subscription.request',
                    'res_id': subscription_id,
                    'datas': base64.encodestring(field_value.read()),
                    'datas_fname': field_value.filename,
                }
                request.registry['ir.attachment'].create(request.cr, SUPERUSER_ID, attachment_value, context=request.context)
        
        return self.get_subscription_response(values, kwargs)

