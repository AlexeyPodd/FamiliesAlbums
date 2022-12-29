from django import template

register = template.Library()


@register.filter
def add_attrs(field, css):
    """For a form field, adds the value passed to the selected arguments.
    The css parameter should be passed like this:
     '<arg1>:<value1>,<arg2>:<value2>,...,<argN>:<valueN>'"""
    attrs = field.field.widget.attrs
    adding_attrs = css.split(',')

    for adding in adding_attrs:
        if ':' not in adding:
            key, val = 'class', adding
        else:
            key, val = adding.split(':')

        if key not in attrs:
            attrs[key] = val
        else:
            attrs[key] = f'{attrs[key]} {val}'

    return field.as_widget(attrs=attrs)
