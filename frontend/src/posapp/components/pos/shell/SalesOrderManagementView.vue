<template>
	<v-container fluid class="sales-order-management">
		<v-row>
			<v-col cols="12">
				<div class="page-header">
					<div>
						<h1 class="page-title">{{ __("Sales Order Management") }}</h1>
						<p class="page-subtitle">
							{{ __("Browse RFS Sales Orders, review due dates, and update key order details.") }}
						</p>
					</div>
				</div>
			</v-col>
		</v-row>

		<v-row v-if="!profileReady">
			<v-col cols="12">
				<v-card class="pos-themed-card">
					<v-card-text class="text-medium-emphasis">
						{{ __("Loading POS profile...") }}
					</v-card-text>
				</v-card>
			</v-col>
		</v-row>

		<v-row v-else-if="!canAccess">
			<v-col cols="12">
				<v-alert type="warning" variant="tonal" border="start">
					{{ __("This page is only available when Select S.O is enabled for the current POS Profile.") }}
				</v-alert>
			</v-col>
		</v-row>

		<v-row v-else class="content-grid">
			<v-col cols="12" lg="4" class="left-panel-col">
				<v-card class="pos-themed-card left-panel">
					<v-card-title class="panel-title">
						<span>{{ __("RFS Sales Orders") }}</span>
						<v-btn
							icon="mdi-refresh"
							variant="text"
							size="small"
							:loading="listLoading"
							@click="loadOrders"
						/>
					</v-card-title>
					<v-card-text class="left-panel-body">
						<div class="search-row">
							<v-text-field
								v-model="searchTerm"
								:label="__('Order, Customer, Payment Ref or Postcode')"
								density="compact"
								hide-details
								clearable
								class="pos-themed-input"
								@keyup.enter="loadOrders"
							/>
							<v-btn color="primary" :loading="listLoading" @click="loadOrders">
								{{ __("Search") }}
							</v-btn>
						</div>
						<div class="filter-row mt-4">
							<v-select
								v-model="selectedPosProfile"
								:items="posProfileFilterItems"
								item-title="title"
								item-value="value"
								:label="__('POS Profile')"
								density="compact"
								hide-details
								class="pos-themed-input"
								@update:model-value="loadOrders"
							/>
							<v-select
								v-model="selectedStatus"
								:items="statusFilterItems"
								item-title="title"
								item-value="value"
								:label="__('Status')"
								density="compact"
								hide-details
								class="pos-themed-input"
								@update:model-value="loadOrders"
							/>
							<v-select
								v-model="selectedSortBy"
								:items="sortByItems"
								item-title="title"
								item-value="value"
								:label="__('Sort By')"
								density="compact"
								hide-details
								class="pos-themed-input"
								@update:model-value="loadOrders"
							/>
						</div>
						<v-alert
							v-if="listError"
							type="error"
							variant="tonal"
							density="compact"
							border="start"
							class="mt-4"
						>
							{{ listError }}
						</v-alert>
						<div v-if="listLoading" class="panel-placeholder">
							{{ __("Loading sales orders...") }}
						</div>
						<div v-else-if="!orders.length" class="panel-placeholder">
							{{ __("No Sales Orders found.") }}
						</div>
						<div v-else class="order-list">
							<button
								v-for="order in orders"
								:key="order.name"
								type="button"
								class="order-list-item"
								:class="{ 'order-list-item--active': order.name === selectedOrderName }"
								@click="selectOrder(order.name)"
							>
								<div class="order-list-item__top">
									<strong>{{ order.customer_name || order.customer }}</strong>
									<span>{{ order.status || __("Unknown") }}</span>
								</div>
								<div class="order-list-item__meta">
									<span>{{ order.name }}</span>
									<span>{{ formatDate(order.transaction_date) }}</span>
								</div>
								<div class="order-list-item__meta">
									<span>{{ __("Preferred") }}: {{ formatDate(order.prefered_earliest_delivery_date) }}</span>
									<span>{{ formatCurrency(order.grand_total, order.currency) }}</span>
								</div>
							</button>
						</div>
					</v-card-text>
				</v-card>
			</v-col>

			<v-col cols="12" lg="8" class="right-panel-col">
				<v-card class="pos-themed-card right-panel">
					<v-card-title class="panel-title">
						<span>{{
							selectedOrder
								? selectedOrder.customer_name || selectedOrder.customer
								: __("Sales Order Details")
						}}</span>
						<div class="panel-actions">
							<template v-if="streamPickLists.length">
								<v-select
									v-model="selectedStreamPickList"
									:items="streamPickListItems"
									item-title="title"
									item-value="value"
									:label="__('Stream Pick List')"
									density="compact"
									hide-details
									class="pos-themed-input stream-select"
								/>
								<v-btn
									color="primary"
									variant="tonal"
									:disabled="!selectedStreamPickListLink"
									@click="openStreamLink"
								>
									{{ __("Open Stream") }}
								</v-btn>
							</template>
							<v-btn
								v-if="canPayRemainingBalance"
								color="success"
								variant="flat"
								:loading="paymentLoading"
								:disabled="paymentLoading"
								@click="openPaymentDialog"
							>
								{{ __("Pay Remaining Balance") }}
							</v-btn>
							<v-btn
								v-if="selectedOrder"
								color="primary"
								variant="tonal"
								prepend-icon="mdi-email-outline"
								:disabled="receiptLoading"
								@click="openReceiptDialog"
							>
								{{ __("Email Receipt") }}
							</v-btn>
							<v-btn
								color="primary"
								:loading="saveLoading"
								:disabled="!selectedOrder || !isDirty"
								@click="saveOrder"
							>
								{{ __("Save") }}
							</v-btn>
						</div>
					</v-card-title>
					<v-card-text class="right-panel-body">
						<v-alert
							v-if="hasSurplus"
							type="warning"
							variant="tonal"
							density="compact"
							border="start"
							class="mb-4"
						>
							{{
								__("This order holds {0} that could not be moved automatically.", [
									formatCurrency(surplus?.amount, selectedOrder?.currency),
								])
							}}
							{{ surplus?.reason }}
						</v-alert>
						<v-alert
							v-if="creditNotice"
							type="info"
							variant="tonal"
							density="compact"
							border="start"
							class="mb-4"
						>
							{{ creditNotice }}
						</v-alert>
						<v-alert
							v-if="detailError"
							type="error"
							variant="tonal"
							density="compact"
							border="start"
							class="mb-4"
						>
							{{ detailError }}
						</v-alert>
						<div v-if="detailLoading" class="panel-placeholder">
							{{ __("Loading order details...") }}
						</div>
						<div v-else-if="!selectedOrder" class="panel-placeholder">
							{{ __("Choose a Sales Order to review and update it.") }}
						</div>
						<div v-else class="detail-grid">
							<div class="detail-summary">
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Sales Order") }}</span>
									<strong>{{ selectedOrder.name }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Status") }}</span>
									<strong>{{ selectedOrder.status || __("Unknown") }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Latest Component Due") }}</span>
									<strong>{{ formatDate(selectedOrder.latest_component_due_date) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Paid") }}</span>
									<strong>{{ formatCurrency(selectedOrder.advance_paid, selectedOrder.currency) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Outstanding") }}</span>
									<strong>{{ formatCurrency(selectedOrder.outstanding_balance, selectedOrder.currency) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Auto Release") }}</span>
									<strong>{{ formatDate(selectedOrder.auto_release_date) }}</strong>
								</div>
							</div>

							<v-tabs v-model="detailTab" color="primary" class="detail-tabs">
								<v-tab value="details">{{ __("Details") }}</v-tab>
								<v-tab value="address">{{ __("Address") }}</v-tab>
							</v-tabs>

							<v-window v-model="detailTab" class="detail-window">
							<v-window-item value="details">
							<v-row dense>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.customer_name || selectedOrder.customer"
										:label="__('Customer')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.customer_order_ref || ''"
										:label="__('Payment Ref')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										v-model="form.customer_ref"
										:label="__('Customer Ref')"
										density="compact"
										hide-details
										class="pos-themed-input"
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="formatDate(selectedOrder.transaction_date)"
										:label="__('Transaction Date')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<VueDatePicker
										:model-value="form.prefered_earliest_delivery_date || null"
										model-type="yyyy-MM-dd"
										format="dd-MM-yyyy"
										:enable-time-picker="false"
										auto-apply
										class="sleek-field pos-themed-input"
										:placeholder="__('Preferred Delivery Date')"
										@update:model-value="
											form.prefered_earliest_delivery_date = ($event as string | null) || ''
										"
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.shipping_address_name || ''"
										:label="__('Shipping Address')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col v-if="selectedOrder.shipping_address_mobile" cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.shipping_address_mobile"
										:label="__('Shipping Address Mobile')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="deliveryChargeDisplay"
										:label="__('Delivery Charge')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="salesPersonDisplay"
										:label="__('POS Sales Person')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="paymentTypesDisplay"
										:label="__('Payment Type')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12">
									<v-textarea
										v-model="form.posa_notes"
										:label="__('Notes')"
										rows="4"
										auto-grow
										hide-details
										class="pos-themed-input"
									/>
								</v-col>
							</v-row>

							<div class="items-section">
								<div class="items-section__header">
									<div class="items-section__heading">
										<h3>{{ __("Items") }}</h3>
										<span>{{ __("Unlocked rows can be updated here. Picked, delivered, or linked pick-list rows are read only.") }}</span>
									</div>
									<v-btn
										color="primary"
										variant="tonal"
										prepend-icon="mdi-plus"
										:loading="addItemLoading"
										:disabled="!canEditItems || saveLoading"
										@click="itemSelectorOpen = true"
									>
										{{ __("Add Items") }}
									</v-btn>
								</div>
								<v-alert
									v-if="orderLevelLock?.is_locked"
									type="warning"
									variant="tonal"
									density="compact"
									border="start"
									class="mb-3"
								>
									{{ orderLevelLock.reason }}
								</v-alert>
								<div class="items-table-wrapper">
									<v-table density="compact">
										<thead>
											<tr>
												<th>{{ __("Item") }}</th>
												<th>{{ __("Qty") }}</th>
												<th>{{ __("Picked") }}</th>
												<th>{{ __("Delivered") }}</th>
												<th>{{ __("Rate") }}</th>
												<th>{{ __("Component Due Date") }}</th>
												<th>{{ __("Status") }}</th>
												<th>{{ __("Actions") }}</th>
											</tr>
										</thead>
										<tbody>
											<tr v-for="item in editableItems" :key="item.rowKey">
												<td>
													<div class="item-cell">
														<strong>{{ item.item_name }}</strong>
														<span>{{ item.item_code }}</span>
														<span>{{ item.description || __("No description") }}</span>
														<span v-if="item.lock_reason" class="item-lock-reason">
															{{ item.lock_reason }}
														</span>
													</div>
												</td>
												<td>
													<input
														v-model.number="item.qty"
														class="items-input"
														type="number"
														autocomplete="off"
														min="0.01"
														step="0.01"
														:readonly="item.is_locked || !canEditItems || saveLoading"
														@blur="normalizeQty(item)"
													/>
												</td>
												<td>{{ item.picked_qty ?? 0 }}</td>
												<td>{{ item.delivered_qty }}</td>
												<td>
													<!-- Only a row being added is priceable here. Rows already on the
													     order keep their price, which the server enforces as well. -->
													<template v-if="item.is_new">
														<input
															v-model.number="item.rate"
															class="items-input"
															type="number"
															autocomplete="off"
															min="0"
															step="0.01"
															:readonly="!canEditItems || saveLoading"
															@blur="normalizeRate(item)"
														/>
														<span class="item-line-amount">
															{{
																formatCurrency(
																	Number(item.qty || 0) * Number(item.rate || 0),
																	selectedOrder.currency,
																)
															}}
														</span>
													</template>
													<template v-else>
														{{ formatCurrency(item.rate, selectedOrder.currency) }}
													</template>
												</td>
												<td>{{ formatDate(item.component_due_date) }}</td>
												<td>
													<div class="item-status">
														<span
															class="lock-pill"
															:class="
																item.is_new
																	? 'lock-pill--new'
																	: item.is_locked
																		? 'lock-pill--locked'
																		: 'lock-pill--open'
															"
														>
															{{
																item.is_new
																	? __("New")
																	: item.is_locked
																		? __("Locked")
																		: __("Editable")
															}}
														</span>
														<span v-if="item.linked_pick_lists?.length" class="item-status__meta">
															{{ formatPickLists(item.linked_pick_lists) }}
														</span>
													</div>
												</td>
												<td>
													<v-btn
														variant="text"
														color="error"
														size="small"
														:disabled="item.is_locked || !canEditItems || saveLoading"
														@click="removeItem(item.rowKey)"
													>
														{{ __("Remove") }}
													</v-btn>
												</td>
											</tr>
											<tr v-if="!editableItems.length">
												<td colspan="8" class="items-empty-state">
													{{ __("No items available on this Sales Order.") }}
												</td>
											</tr>
										</tbody>
									</v-table>
								</div>
							</div>
							</v-window-item>

							<v-window-item value="address">
								<div v-if="!shippingAddress" class="panel-placeholder">
									{{ __("No shipping address is set on this Sales Order.") }}
								</div>
								<div v-else class="address-panel">
									<div class="address-panel__block">
										<h4>{{ __("Shipping Address") }}</h4>
										<strong>{{ shippingAddress.address_title || shippingAddress.name }}</strong>
										<span v-for="line in shippingAddressLines" :key="line">{{ line }}</span>
									</div>
									<v-row dense>
										<v-col cols="12" md="6">
											<v-text-field
												:model-value="shippingAddress.phone || __('N/A')"
												:label="__('Mobile')"
												density="compact"
												readonly
												hide-details
											/>
										</v-col>
										<v-col cols="12" md="6">
											<v-text-field
												:model-value="shippingAddress.email_id || __('N/A')"
												:label="__('Email')"
												density="compact"
												readonly
												hide-details
											/>
										</v-col>
										<v-col cols="12" md="6">
											<v-text-field
												:model-value="shippingAddress.address_type || __('N/A')"
												:label="__('Address Type')"
												density="compact"
												readonly
												hide-details
											/>
										</v-col>
										<v-col cols="12" md="6">
											<v-text-field
												:model-value="shippingAddress.name"
												:label="__('Address Record')"
												density="compact"
												readonly
												hide-details
											/>
										</v-col>
									</v-row>
								</div>
							</v-window-item>
							</v-window>
						</div>
					</v-card-text>
				</v-card>
			</v-col>
		</v-row>

		<v-dialog v-model="paymentDialogOpen" max-width="460">
			<v-card class="pos-themed-card">
				<v-card-title>{{ __("Pay Remaining Balance") }}</v-card-title>
				<v-card-text class="pt-2">
					<v-alert
						v-if="paymentError"
						type="error"
						variant="tonal"
						density="compact"
						border="start"
						class="mb-4"
					>
						{{ paymentError }}
					</v-alert>
					<div class="payment-balance-copy mb-4">
						<span class="payment-balance-copy__label">{{ __("Remaining Balance") }}</span>
						<strong class="payment-balance-copy__amount">
							{{ formatCurrency(selectedOrder?.outstanding_balance, selectedOrder?.currency) }}
						</strong>
					</div>
					<v-text-field
						v-model="paymentForm.amount"
						:label="__('Payment Amount')"
						density="compact"
						hide-details
						type="number"
						step="0.01"
						min="0"
						class="pos-themed-input mb-4"
					/>
					<v-select
						v-model="paymentForm.mode_of_payment"
						:items="paymentModeOptions"
						item-title="label"
						item-value="value"
						:label="__('Mode of Payment')"
						density="compact"
						hide-details
						class="pos-themed-input mb-4"
					/>
					<v-text-field
						v-model="paymentForm.reference_no"
						:label="__('Reference No')"
						density="compact"
						readonly
						hide-details
						class="pos-themed-input"
					/>
				</v-card-text>
				<v-card-actions class="justify-end">
					<v-btn variant="text" @click="closePaymentDialog">
						{{ __("Cancel") }}
					</v-btn>
					<v-btn
						color="success"
						variant="flat"
						:loading="paymentLoading"
						:disabled="paymentLoading || !paymentForm.mode_of_payment"
						@click="submitRemainingBalancePayment"
					>
						{{ __("Pay Now") }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>

		<!-- Resending is a deliberate act, so the recipient is shown and editable before
		     anything is queued rather than the receipt silently going wherever the order
		     happens to point. -->
		<v-dialog v-model="receiptDialogOpen" max-width="520">
			<v-card class="pos-themed-card">
				<v-card-title>{{ __("Email Receipt") }}</v-card-title>
				<v-card-text class="pt-2">
					<v-alert
						v-if="receiptError"
						type="error"
						variant="tonal"
						density="compact"
						border="start"
						class="mb-4"
					>
						{{ receiptError }}
					</v-alert>
					<v-alert
						v-if="receiptBlockedReason"
						type="warning"
						variant="tonal"
						density="compact"
						border="start"
						class="mb-4"
					>
						{{ receiptBlockedReason }}
					</v-alert>
					<p class="mb-4">
						{{
							__("The receipt for {0} will be attached as a PDF and sent again.", [
								selectedOrder?.name || "",
							])
						}}
					</p>
					<!-- The address is what the send resolves through, so name it rather than
					     letting the field look like a free-text "send to" box. -->
					<div class="payment-balance-copy mb-4">
						<span class="payment-balance-copy__label">{{ __("Currently sends to") }}</span>
						<strong>{{ receiptCurrentRecipient }}</strong>
					</div>
					<v-select
						v-if="receiptAddressOptions.length > 1"
						v-model="receiptForm.address"
						:items="receiptAddressOptions"
						item-title="title"
						item-value="value"
						:label="__('Address to update')"
						density="compact"
						hide-details
						class="pos-themed-input mb-4"
						@update:model-value="onReceiptAddressChange"
					/>
					<v-text-field
						v-if="receiptAddressOptions.length"
						v-model="receiptForm.email"
						:label="receiptEmailLabel"
						:hint="receiptEmailHint"
						persistent-hint
						density="compact"
						type="email"
						class="pos-themed-input"
					/>
					<!-- Opt-in: a resend is usually a fix for one customer, so the office
					     copy is off unless it is asked for. -->
					<v-checkbox
						v-if="receiptCcEmails.length"
						v-model="receiptForm.includeCc"
						:label="__('Also send a copy to {0}', [receiptCcEmails.join(', ')])"
						density="compact"
						hide-details
						class="mt-2"
					/>
				</v-card-text>
				<v-card-actions class="justify-end">
					<v-btn variant="text" :disabled="receiptLoading" @click="closeReceiptDialog">
						{{ __("Cancel") }}
					</v-btn>
					<v-btn
						color="primary"
						variant="flat"
						:loading="receiptLoading"
						:disabled="receiptLoading || !receiptCanSend"
						@click="sendReceipt"
					>
						{{ receiptEmailChanged ? __("Update Email and Send") : __("Send Receipt") }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>

		<!-- Kept out of the two column layout: the selector needs real width, and the
		     detail panel is already tight. -->
		<v-navigation-drawer
			v-model="itemSelectorOpen"
			location="right"
			temporary
			width="520"
			class="item-selector-drawer"
		>
			<div class="item-selector-drawer__header">
				<h3>{{ __("Add Items") }}</h3>
				<v-btn
					icon="mdi-close"
					variant="text"
					density="comfortable"
					:aria-label="__('Close item selector')"
					@click="itemSelectorOpen = false"
				/>
			</div>
			<div class="item-selector-drawer__body">
				<ItemsSelector v-if="itemSelectorOpen" context="sales-order" @add-item="onAddItem" />
			</div>
		</v-navigation-drawer>

		<!-- Payment before save: the rows are only written once this succeeds, so
		     cancelling leaves the edits staged and the order untouched. -->
		<v-dialog v-model="itemPaymentDialogOpen" max-width="480" persistent>
			<v-card class="pos-themed-card">
				<v-card-title>{{ __("Payment Required") }}</v-card-title>
				<v-card-text class="pt-2">
					<v-alert v-if="itemPaymentError" type="error" variant="tonal" density="compact" border="start" class="mb-4">
						{{ itemPaymentError }}
					</v-alert>
					<p class="mb-4">
						{{ __("These changes increase the order total. Payment is needed before the items are saved.") }}
					</p>
					<div class="payment-balance-copy mb-2">
						<span class="payment-balance-copy__label">{{ __("New Order Total") }}</span>
						<strong>{{ formatCurrency(itemPaymentPreview?.projected_grand_total, selectedOrder?.currency) }}</strong>
					</div>
					<div class="payment-balance-copy mb-2">
						<span class="payment-balance-copy__label">{{ __("Already Paid") }}</span>
						<strong>{{ formatCurrency(itemPaymentPreview?.advance_paid, selectedOrder?.currency) }}</strong>
					</div>
					<div v-if="useCustomerCredit" class="payment-balance-copy mb-2">
						<span class="payment-balance-copy__label">{{ __("Credit Applied") }}</span>
						<strong>-{{ formatCurrency(creditApplicable, selectedOrder?.currency) }}</strong>
					</div>
					<div class="payment-balance-copy mb-4">
						<span class="payment-balance-copy__label">{{ __("To Take Now") }}</span>
						<strong class="payment-balance-copy__amount">
							{{ formatCurrency(itemPaymentTillAmount, selectedOrder?.currency) }}
						</strong>
					</div>
					<!-- advance_paid only sees money allocated to THIS order, so offer the
						     customer's own money before taking more from them. -->
						<v-alert
							v-if="creditApplicable > 0.001"
							type="info"
							variant="tonal"
							density="compact"
							border="start"
							class="mb-4"
						>
							<v-checkbox
								v-model="useCustomerCredit"
								:disabled="itemPaymentLoading"
								density="compact"
								hide-details
								:label="
									__('Apply {0} of the customer\u2019s {1} credit', [
										formatCurrency(creditApplicable, selectedOrder?.currency),
										formatCurrency(
											itemPaymentPreview?.customer_credit?.unallocated_payments,
											selectedOrder?.currency,
										),
									])
								"
							/>
						</v-alert>
					<v-select
						v-if="itemPaymentTillAmount > 0.001"
						v-model="itemPaymentMode"
						:items="paymentModeOptions"
						item-title="label"
						item-value="value"
						:label="__('Mode of Payment')"
						density="compact"
						hide-details
						class="pos-themed-input"
					/>
				</v-card-text>
				<v-card-actions>
					<v-spacer />
					<v-btn variant="text" :disabled="itemPaymentLoading" @click="closeItemPaymentDialog">
						{{ __("Cancel") }}
					</v-btn>
					<v-btn
						color="success"
						variant="flat"
						:loading="itemPaymentLoading"
						:disabled="(itemPaymentTillAmount > 0 && !itemPaymentMode) || itemPaymentLoading"
						@click="confirmItemPayment"
					>
						{{ itemPaymentTillAmount > 0.001 ? __("Take Payment and Save") : __("Apply Credit and Save") }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</v-container>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import api from "../../../services/api";
import ItemsSelector from "../items/ItemsSelector.vue";
import { useToastStore } from "../../../stores/toastStore.js";
import { useUIStore } from "../../../stores/uiStore.js";
import { storeToRefs } from "pinia";

declare const __: (value: string, args?: any[]) => string;

type ManagedSalesOrderListRow = {
	name: string;
	customer?: string;
	customer_name?: string;
	status?: string;
	transaction_date?: string | null;
	prefered_earliest_delivery_date?: string | null;
	customer_ref?: string | null;
	customer_order_ref?: string | null;
	currency?: string | null;
	pos_profile?: string | null;
	grand_total?: number | null;
	rounded_total?: number | null;
	advance_paid?: number | null;
	outstanding_balance?: number | null;
	modified?: string | null;
};

type ManagedSalesOrderSortKey = "transaction_date" | "modified";

type ManagedSalesOrderPosProfile = {
	name: string;
	company?: string | null;
	currency?: string | null;
};

type PickListSummary = {
	name: string;
	status?: string | null;
	docstatus?: number | null;
	per_delivered?: number | null;
};

type ManagedSalesOrderItem = {
	name: string;
	item_code: string;
	item_name?: string | null;
	description?: string | null;
	warehouse?: string | null;
	uom?: string | null;
	qty?: number | null;
	picked_qty?: number | null;
	delivered_qty?: number | null;
	rate?: number | null;
	amount?: number | null;
	conversion_factor?: number | null;
	delivery_date?: string | null;
	component_due_date?: string | null;
	quoted_date?: string | null;
	is_locked?: boolean;
	lock_reason?: string | null;
	linked_pick_lists?: PickListSummary[];
};

/** A row in the local edit buffer. */
type EditableSalesOrderItem = ManagedSalesOrderItem & {
	/** Stable key for v-for and dirty tracking: the docname, or a local id for a row not yet saved. */
	rowKey: string;
	/** True while the row is staged locally and has no Sales Order Item behind it yet. */
	is_new: boolean;
};

type ManagedSalesOrderAddress = {
	name: string;
	address_title?: string | null;
	address_type?: string | null;
	address_line1?: string | null;
	address_line2?: string | null;
	city?: string | null;
	county?: string | null;
	state?: string | null;
	pincode?: string | null;
	country?: string | null;
	email_id?: string | null;
	phone?: string | null;
	display?: string | null;
};

type ManagedSalesOrderReceiptAddress = {
	name: string;
	fieldname?: string;
	label?: string;
	address_title?: string | null;
	email_id?: string | null;
};

type ManagedSalesOrderReceiptEmail = {
	print_format?: string | null;
	recipient?: string | null;
	recipient_address?: string | null;
	addresses?: ManagedSalesOrderReceiptAddress[] | null;
	cc_emails?: string[] | null;
	can_send?: boolean;
	blocked_reason?: string | null;
};

type ManagedSalesOrderSurplus = {
	amount?: number | null;
	reason?: string | null;
};

type ManagedSalesOrderOrderLevelLock = {
	is_locked?: boolean;
	reason?: string | null;
};

type ManagedSalesOrderStreamPickList = {
	name: string;
	status?: string | null;
	stream_id?: string | null;
	stream_status?: string | null;
	tracking_link: string;
};

type ManagedSalesOrderPaymentType = {
	mode_of_payment: string;
	amount?: number | null;
};

type ManagedSalesOrderDetail = ManagedSalesOrderListRow & {
	delivery_charge?: string | null;
	delivery_charge_rate?: number | null;
	pos_sales_person?: string | null;
	pos_sales_person_name?: string | null;
	payment_types?: ManagedSalesOrderPaymentType[] | null;
	stream_pick_lists?: ManagedSalesOrderStreamPickList[] | null;
	order_level_lock?: ManagedSalesOrderOrderLevelLock | null;
	surplus?: ManagedSalesOrderSurplus | null;
	shipping_address?: ManagedSalesOrderAddress | null;
	shipping_address_mobile?: string | null;
	receipt_email?: ManagedSalesOrderReceiptEmail | null;
	auto_release_date?: string | null;
	shipping_address_name?: string | null;
	customer_address?: string | null;
	posa_notes?: string | null;
	shopify_notes?: string | null;
	latest_component_due_date?: string | null;
	advance_paid?: number | null;
	outstanding_balance?: number | null;
	items?: ManagedSalesOrderItem[];
};

const uiStore = useUIStore();
const toastStore = useToastStore();
const { posProfile } = storeToRefs(uiStore);

const profileReady = computed(() => Boolean(posProfile.value?.name));
const canAccess = computed(() => Number(posProfile.value?.custom_allow_select_sales_order || 0) === 1);

const orders = ref<ManagedSalesOrderListRow[]>([]);
const selectedOrder = ref<ManagedSalesOrderDetail | null>(null);
const selectedOrderName = ref("");
const searchTerm = ref("");
const posProfileOptions = ref<ManagedSalesOrderPosProfile[]>([]);
const selectedPosProfile = ref("");
const selectedSortBy = ref<ManagedSalesOrderSortKey>("transaction_date");
const statusOptions = ref<string[]>([]);
const selectedStatus = ref("");
const selectedStreamPickList = ref("");
const detailTab = ref("details");
const editableItems = ref<EditableSalesOrderItem[]>([]);
const itemSelectorOpen = ref(false);
const addItemLoading = ref(false);
let localRowCounter = 0;
const nextLocalRowKey = () => `local-${++localRowCounter}`;
const listLoading = ref(false);
const detailLoading = ref(false);
const saveLoading = ref(false);
const paymentLoading = ref(false);
const listError = ref("");
const detailError = ref("");
const paymentDialogOpen = ref(false);
const paymentError = ref("");

// Payment-before-save flow: an edit that raises the order total must be paid for
// before the rows are written, so a cancelled payment leaves nothing saved.
const itemPaymentDialogOpen = ref(false);
const itemPaymentPreview = ref<any>(null);
const itemPaymentMode = ref("");
const itemPaymentError = ref("");
const itemPaymentLoading = ref(false);
// Opt-in: spending a customer's credit is their decision, not a silent netting off.
const useCustomerCredit = ref(false);
const creditNotice = ref("");

// Resend receipt: the recipient is confirmed (and can be corrected on the Address)
// before anything is queued.
const receiptDialogOpen = ref(false);
const receiptLoading = ref(false);
const receiptError = ref("");
const receiptForm = reactive({
	address: "",
	email: "",
	includeCc: false,
});

const paymentForm = reactive({
	amount: "",
	mode_of_payment: "",
	reference_no: "",
});

const form = reactive({
	customer_ref: "",
	prefered_earliest_delivery_date: "",
	posa_notes: "",
});

const cloneEditableItems = (items?: ManagedSalesOrderItem[] | null): EditableSalesOrderItem[] =>
	(Array.isArray(items) ? items : []).map((item) => ({
		name: item.name,
		rowKey: item.name,
		is_new: false,
		item_code: item.item_code,
		item_name: item.item_name ?? "",
		description: item.description ?? "",
		warehouse: item.warehouse ?? "",
		uom: item.uom ?? "",
		qty: Number(item.qty || 0),
		picked_qty: Number(item.picked_qty || 0),
		delivered_qty: Number(item.delivered_qty || 0),
		rate: Number(item.rate || 0),
		amount: Number(item.amount || 0),
		conversion_factor: Number(item.conversion_factor || 1),
		delivery_date: item.delivery_date ?? "",
		component_due_date: item.component_due_date ?? "",
		quoted_date: item.quoted_date ?? "",
		is_locked: Boolean(item.is_locked),
		lock_reason: item.lock_reason ?? "",
		linked_pick_lists: Array.isArray(item.linked_pick_lists)
			? item.linked_pick_lists.map((link) => ({ ...link }))
			: [],
	}));

const resetForm = (order: ManagedSalesOrderDetail | null) => {
	form.customer_ref = String(order?.customer_ref || "");
	form.prefered_earliest_delivery_date = String(order?.prefered_earliest_delivery_date || "");
	form.posa_notes = String(order?.posa_notes || "");
	editableItems.value = cloneEditableItems(order?.items);
	const streamLists = Array.isArray(order?.stream_pick_lists) ? order.stream_pick_lists : [];
	selectedStreamPickList.value = streamLists[0]?.name || "";
	detailTab.value = "details";
};

const isHeaderDirty = computed(() => {
	if (!selectedOrder.value) return false;
	return (
		form.customer_ref !== String(selectedOrder.value.customer_ref || "") ||
		form.prefered_earliest_delivery_date !==
			String(selectedOrder.value.prefered_earliest_delivery_date || "") ||
		form.posa_notes !== String(selectedOrder.value.posa_notes || "")
	);
});

const normalizeItemForCompare = (item: EditableSalesOrderItem) => ({
	rowKey: String(item.rowKey || item.name || ""),
	item_code: String(item.item_code || ""),
	uom: String(item.uom || ""),
	qty: Number(item.qty || 0),
	conversion_factor: Number(item.conversion_factor || 1),
	description: String(item.description || ""),
});

const isItemDirty = computed(() => {
	// Keyed by rowKey rather than compared positionally: adding or removing a row
	// shifts every later index, which would otherwise report unrelated rows as dirty.
	const baseline = new Map(
		cloneEditableItems(selectedOrder.value?.items).map((item) => [
			String(item.rowKey),
			JSON.stringify(normalizeItemForCompare(item)),
		]),
	);

	for (const item of editableItems.value) {
		if (item.is_new) return true;
		const before = baseline.get(String(item.rowKey));
		if (before === undefined) return true;
		if (before !== JSON.stringify(normalizeItemForCompare(item))) return true;
		baseline.delete(String(item.rowKey));
	}

	// Anything still in the baseline was removed.
	return baseline.size > 0;
});

const isDirty = computed(() => isHeaderDirty.value || isItemDirty.value);

const orderLevelLock = computed(() => selectedOrder.value?.order_level_lock || null);

// Adding or changing items is refused server side while a Pick List is active on the
// whole order, so disable it here rather than letting the save fail.
const canEditItems = computed(
	() => Boolean(selectedOrder.value) && !orderLevelLock.value?.is_locked,
);

// Only ever populated when settling could not run - money that reached the order
// without a payment reference to trim. Everything else is settled on save.
const surplus = computed(() => selectedOrder.value?.surplus || null);
const hasSurplus = computed(() => Number(surplus.value?.amount || 0) > 0);

const paymentModeOptions = computed(() =>
	(Array.isArray(posProfile.value?.payments) ? posProfile.value.payments : [])
		.map((row: any) => {
			const mode = String(row?.mode_of_payment || "").trim();
			if (!mode) return null;
			return {
				label: mode,
				value: mode,
			};
		})
		.filter(Boolean) as Array<{ label: string; value: string }>,
);

const canPayRemainingBalance = computed(
	() => Number(selectedOrder.value?.outstanding_balance || 0) > 0.001 && paymentModeOptions.value.length > 0,
);

const sortByItems = computed(() => [
	{ title: __("Order Date (newest first)"), value: "transaction_date" },
	{ title: __("Last Modified (newest first)"), value: "modified" },
]);

const statusFilterItems = computed(() => [
	{ title: __("All Statuses"), value: "" },
	...statusOptions.value.map((status) => ({ title: __(status), value: status })),
]);

const shippingAddress = computed(() => selectedOrder.value?.shipping_address || null);

const shippingAddressLines = computed(() => {
	const address = shippingAddress.value;
	if (!address) return [];
	return [
		address.address_line1,
		address.address_line2,
		address.city,
		address.county,
		address.state,
		address.pincode,
		address.country,
	]
		.map((part) => String(part || "").trim())
		.filter(Boolean);
});

const streamPickLists = computed(() =>
	Array.isArray(selectedOrder.value?.stream_pick_lists) ? selectedOrder.value.stream_pick_lists : [],
);

const streamPickListItems = computed(() =>
	streamPickLists.value.map((pickList) => {
		const context = [pickList.stream_status, pickList.stream_id].filter(Boolean).join(" · ");
		return {
			title: context ? `${pickList.name} (${context})` : pickList.name,
			value: pickList.name,
		};
	}),
);

const selectedStreamPickListLink = computed(
	() =>
		streamPickLists.value.find((pickList) => pickList.name === selectedStreamPickList.value)?.tracking_link ||
		"",
);

const openStreamLink = () => {
	const link = selectedStreamPickListLink.value;
	if (!link) return;
	window.open(link, "_blank", "noopener,noreferrer");
};

const deliveryChargeDisplay = computed(() => {
	const label = String(selectedOrder.value?.delivery_charge || "").trim();
	if (!label) return __("None");
	const rate = Number(selectedOrder.value?.delivery_charge_rate || 0);
	return rate ? `${label} (${formatCurrency(rate, selectedOrder.value?.currency)})` : label;
});

const salesPersonDisplay = computed(
	() =>
		String(selectedOrder.value?.pos_sales_person_name || selectedOrder.value?.pos_sales_person || "").trim() ||
		__("N/A"),
);

const paymentTypesDisplay = computed(() => {
	const payments = selectedOrder.value?.payment_types;
	if (!Array.isArray(payments) || !payments.length) return __("No payments recorded");
	return payments
		.map((payment) =>
			payment.amount
				? `${payment.mode_of_payment} (${formatCurrency(payment.amount, selectedOrder.value?.currency)})`
				: payment.mode_of_payment,
		)
		.join(", ");
});

const posProfileFilterItems = computed(() => [
	{ title: __("All Profiles"), value: "" },
	...posProfileOptions.value.map((profile) => ({ title: profile.name, value: profile.name })),
]);

const formatDate = (value?: string | null) => {
	if (!value) return __("N/A");
	const parsed = new Date(`${value}T00:00:00`);
	if (Number.isNaN(parsed.getTime())) {
		return value;
	}
	return new Intl.DateTimeFormat("en-GB", {
		day: "2-digit",
		month: "2-digit",
		year: "numeric",
	}).format(parsed);
};

const formatCurrency = (value?: number | null, currency?: string | null) => {
	const amount = Number(value || 0);
	try {
		return new Intl.NumberFormat(undefined, {
			style: "currency",
			currency: currency || posProfile.value?.currency || "GBP",
			maximumFractionDigits: 2,
		}).format(amount);
	} catch {
		return amount.toFixed(2);
	}
};

const formatPickLists = (linkedPickLists?: PickListSummary[]) =>
	(Array.isArray(linkedPickLists) ? linkedPickLists : [])
		.map((link) => `${link.name} (${link.status || __("Unknown")})`)
		.join(", ");

const getErrorMessage = (error: any, fallback: string) =>
	error?.message?.message || error?.message || error?.exc || fallback;

const syncSelectedListRow = (detail: ManagedSalesOrderDetail) => {
	const index = orders.value.findIndex((entry) => entry.name === detail.name);
	if (index === -1) return;
	const existing = orders.value[index];
	if (!existing) return;
	orders.value.splice(index, 1, {
		...existing,
		customer_ref: detail.customer_ref,
		prefered_earliest_delivery_date: detail.prefered_earliest_delivery_date,
		advance_paid: detail.advance_paid,
		outstanding_balance: detail.outstanding_balance,
		modified: detail.modified,
	});
};

const removeItem = (rowKey: string) => {
	editableItems.value = editableItems.value.filter((item) => item.rowKey !== rowKey);
};

const onAddItem = async (item: any) => {
	if (!item?.item_code || !selectedOrder.value || saveLoading.value || !canEditItems.value) return;

	const uom = String(item.uom || item.stock_uom || "");
	// Only merge into rows still staged locally. Bumping the qty of a row already on
	// the order would be a silent edit of an existing line.
	const pending = editableItems.value.find(
		(row) => row.is_new && row.item_code === item.item_code && String(row.uom || "") === uom,
	);
	if (pending) {
		pending.qty = Number(pending.qty || 0) + 1;
		return;
	}

	addItemLoading.value = true;
	detailError.value = "";

	try {
		const details = await api.call<any>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_order_new_item_details",
			{
				sales_order: selectedOrder.value.name,
				item_code: item.item_code,
				uom: uom || null,
			},
		);
		if (!details) return;

		editableItems.value.push({
			name: "",
			rowKey: nextLocalRowKey(),
			is_new: true,
			item_code: details.item_code,
			item_name: details.item_name ?? "",
			// Sent back on save: update_child_qty_rate assigns description
			// unconditionally, so dropping it would blank the saved line.
			description: details.description ?? "",
			warehouse: "",
			uom: details.uom ?? "",
			qty: 1,
			picked_qty: 0,
			delivered_qty: 0,
			rate: Number(details.rate || 0),
			amount: Number(details.rate || 0),
			conversion_factor: Number(details.conversion_factor || 1),
			delivery_date: details.delivery_date ?? "",
			component_due_date: "",
			quoted_date: "",
			is_locked: false,
			lock_reason: "",
			linked_pick_lists: [],
		});
	} catch (error: any) {
		console.error("Failed to price the item being added", error);
		detailError.value = getErrorMessage(error, __("Unable to add the selected item"));
	} finally {
		addItemLoading.value = false;
	}
};

const normalizeQty = (item: EditableSalesOrderItem) => {
	const qty = Number(item.qty);
	if (!Number.isFinite(qty) || qty <= 0) {
		item.qty = 1;
	}
};

const normalizeRate = (item: EditableSalesOrderItem) => {
	const rate = Number(item.rate);
	if (!Number.isFinite(rate) || rate < 0) {
		item.rate = 0;
	}
};

const closePaymentDialog = () => {
	paymentDialogOpen.value = false;
	paymentError.value = "";
	paymentForm.amount = "";
	paymentForm.mode_of_payment = "";
	paymentForm.reference_no = "";
};

const receiptState = computed(() => selectedOrder.value?.receipt_email || null);

const receiptAddresses = computed(() =>
	Array.isArray(receiptState.value?.addresses) ? receiptState.value.addresses : [],
);

const receiptAddressOptions = computed(() =>
	receiptAddresses.value.map((address) => {
		const name = String(address.address_title || address.name || "");
		const label = String(address.label || "");
		return {
			title: label ? `${label} - ${name}` : name,
			value: address.name,
		};
	}),
);

/** The email currently stored on the address the dialog is pointed at. */
const receiptSelectedAddressEmail = computed(
	() =>
		String(
			receiptAddresses.value.find((address) => address.name === receiptForm.address)?.email_id || "",
		),
);

/** Configured on the POS Profile, delivered as bcc, and only when the box is ticked. */
const receiptCcEmails = computed(() =>
	Array.isArray(receiptState.value?.cc_emails) ? receiptState.value.cc_emails : [],
);

/** True only for a real correction: a non-empty value that differs from what is stored. */
const receiptEmailChanged = computed(() => {
	const typed = receiptForm.email.trim();
	return Boolean(typed) && typed !== receiptSelectedAddressEmail.value.trim();
});

/** Where the receipt lands if the dialog is sent as it stands. */
const receiptCurrentRecipient = computed(
	() =>
		(receiptEmailChanged.value ? receiptForm.email.trim() : String(receiptState.value?.recipient || "")) ||
		__("No email address found"),
);

const receiptCanSend = computed(
	() =>
		Boolean(receiptState.value?.print_format) &&
		(receiptEmailChanged.value || Boolean(receiptState.value?.recipient)),
);

const receiptEmailLabel = computed(() => {
	const address = receiptAddresses.value.find((row) => row.name === receiptForm.address);
	return address?.label ? __("Email on {0}", [String(address.label)]) : __("Email Address");
});

/** Only a missing print format blocks the send outright - a missing email is fixable here. */
const receiptBlockedReason = computed(() => {
	if (!receiptState.value?.print_format) {
		return String(receiptState.value?.blocked_reason || "");
	}
	if (!receiptAddressOptions.value.length) {
		return __("This order has no address record, so the email can only be changed on the customer.");
	}
	return "";
});

const receiptEmailHint = computed(() => {
	if (receiptEmailChanged.value) {
		return __("Saved on the address before the receipt is sent.");
	}
	return receiptSelectedAddressEmail.value
		? __("Stored on this address. Leave it as it is to send there.")
		: __("This address has no email. Enter one to use it, or send to the address above.");
});

const onReceiptAddressChange = () => {
	receiptForm.email = receiptSelectedAddressEmail.value;
};

const openReceiptDialog = () => {
	if (!selectedOrder.value) return;
	receiptError.value = "";
	const state = receiptState.value;
	// Prefer the address the recipient actually resolved from, so an edit changes the
	// record that decides where the receipt goes.
	receiptForm.address =
		String(state?.recipient_address || "") || receiptAddressOptions.value[0]?.value || "";
	receiptForm.email = receiptSelectedAddressEmail.value;
	receiptForm.includeCc = false;
	receiptDialogOpen.value = true;
};

const closeReceiptDialog = () => {
	receiptDialogOpen.value = false;
	receiptError.value = "";
};

const sendReceipt = async () => {
	if (!selectedOrder.value || receiptLoading.value) return;

	const email = receiptForm.email.trim();
	if (!receiptCanSend.value) {
		receiptError.value = __("There is no email address to send this receipt to.");
		return;
	}
	// Only a typed correction writes to the Address. An untouched field means "send it
	// wherever it already goes", which may be the customer record rather than an address.
	if (receiptEmailChanged.value && !receiptForm.address) {
		receiptError.value = __("This order has no address record to save the email on.");
		return;
	}
	const willUpdateAddress = receiptEmailChanged.value;

	receiptLoading.value = true;
	receiptError.value = "";

	try {
		const message = await api.call<{
			status?: string;
			recipient?: string;
			sales_order?: ManagedSalesOrderDetail;
		}>(
			"posawesome.posawesome.api.sales_orders.resend_managed_sales_order_receipt",
			{
				sales_order: selectedOrder.value.name,
				address: willUpdateAddress ? receiptForm.address : null,
				email: willUpdateAddress ? email : null,
				include_cc: receiptForm.includeCc ? 1 : 0,
			},
			{ freeze: true, freeze_message: __("Queueing the receipt...") },
		);

		// Refreshes the receipt state (and any corrected address email) without calling
		// resetForm: a resend changes no item or header field, and resetForm would throw
		// away edits the user still has staged.
		if (message?.sales_order) {
			selectedOrder.value = message.sales_order;
		}

		if (message?.status === "skipped_dev") {
			// The server refuses to email real customers from a dev copy, so say that
			// rather than reporting a receipt that was never queued.
			toastStore.show({
				title: __("Not sent: receipts are disabled on this development site."),
				color: "warning",
			});
		} else {
			toastStore.show({
				title: __("Receipt queued for {0}", [message?.recipient || email]),
				color: "success",
			});
		}
		receiptDialogOpen.value = false;
	} catch (error: any) {
		console.error("Failed to resend the Sales Order receipt", error);
		receiptError.value = getErrorMessage(error, __("Unable to queue the receipt"));
	} finally {
		receiptLoading.value = false;
	}
};

const openPaymentDialog = () => {
	if (!selectedOrder.value) return;
	paymentError.value = "";
	paymentForm.amount = String(selectedOrder.value.outstanding_balance || "");
	paymentForm.mode_of_payment = paymentModeOptions.value[0]?.value || "";
	paymentForm.reference_no = selectedOrder.value.customer_order_ref || selectedOrder.value.name || "";
	paymentDialogOpen.value = true;
};

const loadPosProfileOptions = async () => {
	if (!posProfile.value?.company) {
		return;
	}

	try {
		const message = await api.call<ManagedSalesOrderPosProfile[]>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_order_pos_profiles",
			{ company: posProfile.value.company },
		);
		posProfileOptions.value = Array.isArray(message) ? message : [];
	} catch (error) {
		console.error("Failed to load POS Profiles for Sales Orders filter", error);
	}

	if (!selectedPosProfile.value && posProfile.value?.name) {
		selectedPosProfile.value = posProfile.value.name;
	}
};

const loadStatusOptions = async () => {
	try {
		const message = await api.call<string[]>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_order_statuses",
		);
		statusOptions.value = Array.isArray(message) ? message : [];
	} catch (error) {
		console.error("Failed to load Sales Order statuses for the filter", error);
	}
};

const loadOrders = async () => {
	if (!canAccess.value || !posProfile.value?.company || !posProfile.value?.currency) {
		return;
	}

	listLoading.value = true;
	listError.value = "";

	try {
		const message = await api.call<ManagedSalesOrderListRow[]>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_orders",
			{
				company: posProfile.value.company,
				currency: posProfile.value.currency,
				order_name: searchTerm.value || null,
				pos_profile: selectedPosProfile.value || null,
				sort_by: selectedSortBy.value,
				status: selectedStatus.value || null,
			},
		);
		orders.value = Array.isArray(message) ? message : [];

		if (selectedOrderName.value) {
			const stillExists = orders.value.some((entry) => entry.name === selectedOrderName.value);
			if (stillExists) {
				await selectOrder(selectedOrderName.value);
				return;
			}
		}

		if (orders.value.length) {
			const firstOrder = orders.value[0];
			if (firstOrder?.name) {
				await selectOrder(firstOrder.name);
			}
		} else {
			selectedOrder.value = null;
			selectedOrderName.value = "";
			resetForm(null);
		}
	} catch (error) {
		console.error("Failed to load managed sales orders", error);
		listError.value = __("Unable to fetch Sales Orders");
	} finally {
		listLoading.value = false;
	}
};

const selectOrder = async (name: string) => {
	if (!name || detailLoading.value) return;

	selectedOrderName.value = name;
	detailLoading.value = true;
	detailError.value = "";

	try {
		const message = await api.call<ManagedSalesOrderDetail>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_order",
			{
				sales_order: name,
			},
		);
		selectedOrder.value = message || null;
		resetForm(selectedOrder.value);
	} catch (error) {
		console.error("Failed to load Sales Order detail", error);
		detailError.value = __("Unable to load the selected Sales Order");
	} finally {
		detailLoading.value = false;
	}
};

/** The rows exactly as the server will receive them - shared by preview and save. */
const buildItemPayload = () =>
	editableItems.value.map((item) => ({
		docname: item.is_new ? null : item.name,
		item_code: item.item_code,
		uom: item.uom || null,
		description: item.description || null,
		qty: Number(item.qty || 0),
		conversion_factor: Number(item.conversion_factor || 1),
		...(item.is_new ? { rate: Number(item.rate || 0) } : {}),
	}));

const previewItemChanges = async () => {
	if (!selectedOrder.value) return null;
	const itemError = validateEditableItems();
	if (itemError) {
		detailError.value = itemError;
		return null;
	}
	try {
		return await api.call<any>(
			"posawesome.posawesome.api.sales_orders.preview_managed_sales_order_items",
			{ data: { name: selectedOrder.value.name, items: buildItemPayload() } },
			{ freeze: true, freeze_message: __("Checking the order total...") },
		);
	} catch (error: any) {
		console.error("Failed to preview Sales Order changes", error);
		detailError.value = getErrorMessage(error, __("Unable to check the order total"));
		return null;
	}
};

/** Credit the cashier can offer, already capped server side at what this order needs. */
const creditApplicable = computed(() => Number(itemPaymentPreview.value?.credit_applicable || 0));

/** What the till takes once any offered credit is applied. */
const itemPaymentTillAmount = computed(() => {
	const due = Number(itemPaymentPreview.value?.amount_due || 0);
	return useCustomerCredit.value ? Math.max(due - creditApplicable.value, 0) : due;
});

const closeItemPaymentDialog = () => {
	// Cancelled: nothing was sent, so the edits stay staged and unsaved.
	itemPaymentDialogOpen.value = false;
	itemPaymentPreview.value = null;
	itemPaymentError.value = "";
};

const confirmItemPayment = async () => {
	if (!selectedOrder.value || !itemPaymentMode.value || itemPaymentLoading.value) return;
	itemPaymentLoading.value = true;
	itemPaymentError.value = "";
	try {
		const message = await api.call<any>(
			"posawesome.posawesome.api.sales_orders.update_managed_sales_order_items_with_payment",
			{
				data: {
					name: selectedOrder.value.name,
					items: buildItemPayload(),
					payment: {
						use_credit: useCustomerCredit.value ? 1 : 0,
						mode_of_payment: itemPaymentMode.value,
						reference_no: selectedOrder.value.customer_order_ref || selectedOrder.value.name,
						// Guards against the total moving while the dialog was open.
						expected_amount: Number(itemPaymentPreview.value?.amount_due || 0),
					},
				},
			},
			{ freeze: true, freeze_message: __("Taking payment and updating the order...") },
		);
		const creditApplied = Number(message?.credit_applied || 0);
		selectedOrder.value = message?.sales_order || selectedOrder.value;
		resetForm(selectedOrder.value);
		itemPaymentDialogOpen.value = false;
		itemPaymentPreview.value = null;
		toastStore.show({
			title: creditApplied
				? __("{0} of credit applied. Sales Order updated.", [
						formatCurrency(creditApplied, selectedOrder.value?.currency),
					])
				: __("Payment taken and Sales Order updated"),
			color: "success",
		});
		await loadOrders();
	} catch (error: any) {
		console.error("Failed to take payment for Sales Order changes", error);
		// Server rolls back on failure, so the items are not saved either.
		itemPaymentError.value = getErrorMessage(error, __("Unable to take payment"));
	} finally {
		itemPaymentLoading.value = false;
	}
};

const validateEditableItems = (): string => {
	for (const item of editableItems.value) {
		const label = item.item_name || item.item_code || __("Row");
		if (!item.item_code || !item.uom) {
			return __("Item {0}: item code and UOM are required.", [label]);
		}
		if (!Number.isFinite(Number(item.qty)) || Number(item.qty) <= 0) {
			return __("Item {0}: Qty must be greater than 0.", [label]);
		}
		if (item.is_new && (!Number.isFinite(Number(item.rate)) || Number(item.rate) < 0)) {
			return __("Item {0}: Rate cannot be negative.", [label]);
		}
	}
	return "";
};

const saveOrder = async () => {
	if (!selectedOrder.value || saveLoading.value || !isDirty.value) return;

	if (isItemDirty.value) {
		const itemError = validateEditableItems();
		if (itemError) {
			detailError.value = itemError;
			return;
		}
	}

	// An increase has to be paid for before the rows land. Ask the server what the
	// order would total, rather than trusting a client-side sum: the figure the
	// customer is charged must include tax exactly as the real save computes it.
	if (isItemDirty.value) {
		const preview = await previewItemChanges();
		if (!preview) return;
		if (Number(preview.amount_due || 0) > 0.001) {
			itemPaymentPreview.value = preview;
			itemPaymentMode.value = paymentModeOptions.value[0]?.value || "";
			itemPaymentError.value = "";
			useCustomerCredit.value = false;
			itemPaymentDialogOpen.value = true;
			return;
		}
		// A reduction leaves the customer in credit. POS takes no refund, so make it
		// visible rather than letting it disappear into the order total.
		const credit = Number(preview.credit_after_change || 0);
		// Settled server side on save: the order keeps its own value and the excess
		// moves to the customer's account.
		creditNotice.value =
			credit >= 1
				? __("{0} has been moved to the customer's account.", [
						formatCurrency(credit, selectedOrder.value?.currency),
					])
				: "";
	} else {
		creditNotice.value = "";
	}

	saveLoading.value = true;
	detailError.value = "";
	let itemsChanged = false;

	try {
		const pendingHeader = {
			customer_ref: form.customer_ref,
			prefered_earliest_delivery_date: form.prefered_earliest_delivery_date || null,
			posa_notes: form.posa_notes,
		};

		if (isItemDirty.value) {
			const itemMessage = await api.call<ManagedSalesOrderDetail>(
				"posawesome.posawesome.api.sales_orders.update_managed_sales_order_items",
				{
					data: {
						name: selectedOrder.value.name,
						items: buildItemPayload(),
					},
				},
				{
					freeze: true,
					freeze_message: __("Updating Sales Order items..."),
				},
			);
			selectedOrder.value = itemMessage || selectedOrder.value;
			if (selectedOrder.value) {
				syncSelectedListRow(selectedOrder.value);
			}
			resetForm(selectedOrder.value);
			form.customer_ref = pendingHeader.customer_ref;
			form.prefered_earliest_delivery_date = String(pendingHeader.prefered_earliest_delivery_date || "");
			form.posa_notes = pendingHeader.posa_notes;
			itemsChanged = true;
		}

		if (isHeaderDirty.value) {
			const message = await api.call<ManagedSalesOrderDetail>(
				"posawesome.posawesome.api.sales_orders.update_managed_sales_order",
				{
					data: {
						name: selectedOrder.value.name,
						customer_ref: pendingHeader.customer_ref,
						prefered_earliest_delivery_date: pendingHeader.prefered_earliest_delivery_date,
						posa_notes: pendingHeader.posa_notes,
					},
				},
			);
			selectedOrder.value = message || selectedOrder.value;
		}

		resetForm(selectedOrder.value);
		if (selectedOrder.value) {
			syncSelectedListRow(selectedOrder.value);
		}
		toastStore.show({
			title: __("Sales Order updated"),
			color: "success",
		});
		if (itemsChanged) {
			// Item changes move grand_total and the outstanding balance, both of which
			// the order list and the payment dialog read.
			await loadOrders();
		}
	} catch (error: any) {
		console.error("Failed to update managed Sales Order", error);
		detailError.value = getErrorMessage(error, __("Unable to update the Sales Order"));
	} finally {
		saveLoading.value = false;
	}
};

const submitRemainingBalancePayment = async () => {
	if (!selectedOrder.value || !paymentForm.mode_of_payment) return;

	paymentLoading.value = true;
	paymentError.value = "";

	try {
		const message = await api.call<{
			sales_order: ManagedSalesOrderDetail;
			payment_entry: string;
		}>(
			"posawesome.posawesome.api.sales_orders.pay_managed_sales_order_balance",
			{
				sales_order: selectedOrder.value.name,
				mode_of_payment: paymentForm.mode_of_payment,
				amount: paymentForm.amount,
				reference_no: paymentForm.reference_no || null,
			},
			{
				freeze: true,
				freeze_message: __("Creating payment..."),
			},
		);

		selectedOrder.value = message?.sales_order || selectedOrder.value;
		if (selectedOrder.value) {
			syncSelectedListRow(selectedOrder.value);
		}
		toastStore.show({
								title: __("Payment Entry {0} created", [message?.payment_entry || ""]),
			color: "success",
		});
		closePaymentDialog();
	} catch (error: any) {
		console.error("Failed to pay managed Sales Order balance", error);
		paymentError.value = getErrorMessage(error, __("Unable to create the remaining balance payment"));
	} finally {
		paymentLoading.value = false;
	}
};

watch(
	() => [profileReady.value, canAccess.value, posProfile.value?.company, posProfile.value?.currency],
	async ([ready, access]) => {
		if (ready && access) {
			await Promise.all([loadPosProfileOptions(), loadStatusOptions()]);
			void loadOrders();
		}
	},
	{ immediate: true },
);
</script>

<style scoped>
.sales-order-management {
	padding: 20px;
	height: calc(100dvh - 32px);
	max-height: calc(100dvh - 32px);
	min-height: 0;
	display: flex;
	flex-direction: column;
	box-sizing: border-box;
	overflow: hidden;
}

.page-header {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	gap: 16px;
}

.page-title {
	margin: 0;
	font-size: 1.7rem;
	font-weight: 700;
	color: var(--pos-text-primary);
}

.page-subtitle {
	margin: 6px 0 0;
	color: var(--pos-text-muted);
	max-width: 720px;
}

.content-grid {
	align-items: stretch;
	flex: 1 1 auto;
	min-height: 0;
	max-height: 100%;
	overflow: hidden;
}

.left-panel-col,
.right-panel-col {
	display: flex;
	flex-direction: column;
	height: 100%;
	max-height: 100%;
	min-height: 0;
}

.left-panel,
.right-panel {
	flex: 1 1 auto;
	height: 100%;
	max-height: 100%;
	min-height: 0;
	display: flex;
	flex-direction: column;
}

.left-panel-body,
.right-panel-body {
	flex: 1 1 auto;
	min-height: 0;
	overflow-y: auto;
}

.panel-title {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	border-bottom: 1px solid var(--pos-border);
}

.panel-actions {
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
}

.payment-balance-copy {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 12px 14px;
	border: 1px solid var(--pos-border);
	border-radius: 14px;
	background: var(--pos-surface);
}

.payment-balance-copy__label {
	font-size: 0.85rem;
	color: var(--pos-text-muted);
}

.payment-balance-copy__amount {
	font-size: 1.05rem;
	color: var(--pos-text-primary);
}

.search-row {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto;
	gap: 12px;
	align-items: end;
}

.detail-tabs {
	border-bottom: 1px solid var(--pos-border);
}

.detail-window {
	padding-top: 16px;
}

.address-panel {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.address-panel__block {
	display: flex;
	flex-direction: column;
	gap: 2px;
}

.address-panel__block h4 {
	margin-bottom: 6px;
	font-size: 0.8rem;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--pos-text-muted);
}

.stream-select {
	min-width: 200px;
	max-width: 260px;
}

.filter-row {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
	gap: 12px;
	align-items: end;
}

.panel-placeholder {
	padding: 28px 8px;
	color: var(--pos-text-muted);
	text-align: center;
}

.order-list {
	display: grid;
	gap: 12px;
	margin-top: 16px;
}

.order-list-item {
	border: 1px solid var(--pos-border);
	border-radius: 16px;
	background: var(--pos-surface);
	color: var(--pos-text-primary);
	padding: 14px;
	text-align: left;
	transition:
		border-color 0.18s ease,
		transform 0.18s ease,
		box-shadow 0.18s ease;
}

.order-list-item:hover {
	transform: translateY(-1px);
	border-color: var(--pos-primary);
	box-shadow: 0 8px 18px var(--pos-shadow);
}

.order-list-item--active {
	border-color: var(--pos-primary);
	background: color-mix(in srgb, var(--pos-primary) 8%, var(--pos-surface));
}

.order-list-item__top,
.order-list-item__meta {
	display: flex;
	justify-content: space-between;
	gap: 12px;
}

.order-list-item__top {
	margin-bottom: 6px;
}

.order-list-item__meta {
	color: var(--pos-text-muted);
	font-size: 0.88rem;
}

.detail-grid {
	display: grid;
	gap: 18px;
}

.detail-summary {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
	gap: 12px;
}

.summary-chip {
	border: 1px solid var(--pos-border);
	border-radius: 16px;
	padding: 12px 14px;
	background: var(--pos-surface);
}

.summary-chip__label {
	display: block;
	font-size: 0.82rem;
	color: var(--pos-text-muted);
	margin-bottom: 6px;
}

.items-section {
	display: grid;
	gap: 12px;
}

.items-section__header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 12px;
}

.items-section__heading {
	display: flex;
	flex-direction: column;
	gap: 2px;
}

.items-section__header h3 {
	margin: 0;
	font-size: 1rem;
	color: var(--pos-text-primary);
}

.items-section__header span {
	color: var(--pos-text-muted);
	font-size: 0.85rem;
}

.items-table-wrapper {
	border: 1px solid var(--pos-border);
	border-radius: 18px;
	overflow: hidden;
	background: var(--pos-surface);
}

.item-cell {
	display: grid;
	gap: 4px;
}

.item-cell span {
	color: var(--pos-text-muted);
	font-size: 0.85rem;
}

.item-lock-reason {
	color: var(--v-theme-error);
}

.items-input {
	width: 100%;
	border: 1px solid var(--pos-border);
	border-radius: 10px;
	padding: 8px 10px;
	background: color-mix(in srgb, var(--pos-surface) 88%, white 12%);
	color: var(--pos-text-primary);
}

.items-input[readonly] {
	opacity: 0.7;
	cursor: not-allowed;
}

.item-status {
	display: grid;
	gap: 6px;
}

.item-status__meta {
	font-size: 0.82rem;
	color: var(--pos-text-muted);
}

.lock-pill {
	display: inline-flex;
	align-items: center;
	width: fit-content;
	padding: 4px 10px;
	border-radius: 999px;
	font-size: 0.78rem;
	font-weight: 600;
}

.lock-pill--locked {
	background: color-mix(in srgb, var(--v-theme-error) 14%, transparent);
	color: var(--v-theme-error);
}

.lock-pill--open {
	background: color-mix(in srgb, var(--v-theme-success) 14%, transparent);
	color: var(--v-theme-success);
}

.lock-pill--new {
	background: color-mix(in srgb, var(--v-theme-primary) 16%, transparent);
	color: var(--v-theme-primary);
}

.item-line-amount {
	display: block;
	margin-top: 4px;
	font-size: 0.78rem;
	color: var(--pos-text-muted);
}

.item-selector-drawer__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 12px 16px;
	border-bottom: 1px solid var(--pos-border);
}

.item-selector-drawer__header h3 {
	margin: 0;
	font-size: 1rem;
	color: var(--pos-text-primary);
}

/* The selector sizes itself to its container, so give it the remaining height. */
.item-selector-drawer__body {
	height: calc(100% - 57px);
	overflow: hidden;
}

.items-empty-state {
	padding: 18px;
	color: var(--pos-text-muted);
	text-align: center;
}

@media (max-width: 960px) {
	.search-row {
		grid-template-columns: 1fr;
	}

	.items-section__header {
		flex-direction: column;
		align-items: flex-start;
	}
}

/* Below the `lg` breakpoint the panels stack full-width, so let the page scroll
   naturally instead of constraining each panel to its own scroll region. */
@media (max-width: 1279px) {
	.sales-order-management {
		height: auto;
		max-height: none;
		overflow: visible;
	}

	.content-grid {
		flex: 0 1 auto;
		min-height: auto;
	}

	.left-panel-col,
	.right-panel-col {
		display: block;
	}

	.left-panel,
	.right-panel {
		flex: 0 1 auto;
		height: auto;
	}

	.left-panel-body,
	.right-panel-body {
		overflow-y: visible;
	}
}
</style>
